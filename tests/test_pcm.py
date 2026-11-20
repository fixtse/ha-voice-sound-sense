"""Compile and exercise the actual package lambda, not a second decoder."""
import pathlib
import subprocess
import tempfile
import yaml

class Loader(yaml.SafeLoader):
    pass
Loader.add_constructor('!lambda', lambda loader, node: loader.construct_scalar(node))
package = yaml.load(pathlib.Path('sound_sense.yaml').read_text(), Loader=Loader)
body = next(s for s in package['script'] if s['id'] == 'process_audio_data')['then'][0]['lambda']

def source(bits, channels=1, channel=0, stride=4):
    text = body
    values = dict(package['substitutions'])
    values.update(sound_sense_sample_bits=str(bits), sound_sense_channels=str(channels),
                  sound_sense_channel=str(channel), sound_sense_sample_stride=str(stride),
                  sound_sense_player_idle='idle', sound_sense_capture_allowed='allowed')
    for key, value in values.items():
        text = text.replace('${'+key+'}', value)
    assert '${' not in text
    return text

prefix = '''
#include <algorithm>
#include <atomic>
#include <optional>
#include <string>
#include <ctime>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <vector>
uint32_t clock_ms = 1000;
uint32_t millis(){return clock_ms;}
std::atomic<uint32_t> sound_sense_last_sample_ms{0}, sound_sense_sample_sequence{0};
std::atomic<bool> sound_sense_sample_seen{false}, sound_sense_sample_recent{false};
struct Reading { float state; } ambient_sound_level{0},presence_threshold{30};
struct Now { int64_t timestamp; bool is_valid() const{return true;} };
struct Clock { Now now(){return {1800000000+int64_t(clock_ms/1000)};} } sound_sense_clock;
namespace esphome {
struct ESPTime {
  time_t ts;
  static ESPTime from_epoch_utc(time_t ts){return {ts};}
  std::string strftime(const char *format) {char buf[32];std::strftime(buf,sizeof(buf),format,std::gmtime(&ts));return buf;}
};
}
using std::optional;
float current_sound_level = -1;
bool idle = true, allowed = true;
#define id(x) x
'''
functions = []
for bits in (16, 24, 32):
    for channels, channel in ((1, 0), (2, 0), (2, 1)):
        name = f'pcm_{bits}_{channels}_{channel}'
        functions.append(f'void {name}(std::vector<uint8_t> audio_data) {{\n{source(bits, channels, channel)}\n}}')
def render(text):
    for key,value in package['substitutions'].items():
        text=text.replace('${'+key+'}',str(value))
    return text.replace('${sound_sense_player_id}', 'external_media_player')

fresh = next(x for x in package['binary_sensor'] if x['id']=='sound_measurement_active')['lambda']
classifier = next(x for x in package['text_sensor'] if x['id']=='sound_detection_sensor')['lambda']
stamp = next(x for x in package['text_sensor'] if x['id']=='sound_last_audio_sample')['lambda']
for text,name,return_type in ((fresh,'fresh','bool'),(classifier,'classify','optional<std::string>'),(stamp,'timestamp','optional<std::string>')):
    text=text.replace('${sound_sense_player_idle}','idle').replace('${sound_sense_capture_allowed}','allowed')
    functions.append(f'{return_type} {name}() {{\n'+render(text)+'\n}')

harness = '''
std::vector<uint8_t> pcm(int bits, int channels, int channel, int64_t sample) {
  std::vector<uint8_t> data;
  for (int frame=0;frame<16;++frame) for(int c=0;c<channels;++c) {
    uint32_t value=uint32_t(c==channel ? sample : 0);
    for(int b=0;b<bits/8;++b) data.push_back(uint8_t(value>>(8*b)));
  }
  return data;
}
int main() {
'''
for bits in (16, 24, 32):
    for channels, channel in ((1, 0), (2, 0), (2, 1)):
        name = f'pcm_{bits}_{channels}_{channel}'
        harness += f'''
  for(int64_t value : {{int64_t(0), int64_t(1)<<{bits-2}, -(int64_t(1)<<{bits-2}), -(int64_t(1)<<{bits-1})}}) {{
    auto data=pcm({bits},{channels},{channel},value);
    {name}(data);
    const float actual=current_sound_level;
    pcm_16_1_0(pcm(16,1,0,value / (int64_t(1)<<{bits-16})));
    assert(actual==current_sound_level);
    // Ignore a trailing incomplete frame, including a whole sample of stereo.
    data.insert(data.end(), {bits//8*channels-1}, 255);
    {name}(data); assert(actual==current_sound_level);
  }}
  current_sound_level=-1; {name}({{}}); assert(current_sound_level==-1);
  idle=false; {name}(pcm({bits},{channels},{channel},0)); assert(current_sound_level==-1); idle=true;
  allowed=false; {name}(pcm({bits},{channels},{channel},0)); assert(current_sound_level==-1); allowed=true;
'''
harness += r'''
  clock_ms=10000;idle=allowed=true;pcm_16_1_0(pcm(16,1,0,0));
  assert(fresh()); // Digital silence is a fresh sample, not a missing callback.
  const auto old_stamp=timestamp();const auto seq=sound_sense_sample_sequence.load();
  clock_ms+=1000;assert(timestamp()==old_stamp); // No heartbeat fabricated from polling.
  pcm_16_1_0({});assert(sound_sense_sample_sequence.load()==seq);
  clock_ms+=5000;assert(!fresh());assert(timestamp()==old_stamp);
  pcm_16_1_0(pcm(16,1,0,16384));assert(fresh());assert(timestamp()>old_stamp);
  idle=false;assert(!fresh());idle=true;assert(!fresh()); // Require a new sample after gating.
  pcm_16_1_0(pcm(16,1,0,16384));assert(fresh());
  ambient_sound_level.state=60;allowed=false;assert(classify()==optional<std::string>("unknown"));
  assert(!fresh());allowed=true;
  optional<std::string> last;
  for(int i=0;i<9;++i){clock_ms+=2000;pcm_16_1_0(pcm(16,1,0,16384));auto state=classify();if(state)last=state;}
  assert(last==optional<std::string>("presence"));
  // Re-query returns no change; the classifier has reached presence.
  assert(!classify().has_value());
  idle=false;assert(classify()==optional<std::string>("unknown"));assert(!fresh());
  idle=true;clock_ms+=100;pcm_16_1_0(pcm(16,1,0,16384));
  auto after=classify();assert(!after||*after!="presence"); // No frozen presence after pause.
  clock_ms=UINT32_MAX-1000;pcm_16_1_0(pcm(16,1,0,0));clock_ms=50;assert(fresh());
}
'''
with tempfile.TemporaryDirectory(prefix='soundsense-pcm-') as tmp:
    cpp = pathlib.Path(tmp)/'test.cpp'
    binary = pathlib.Path(tmp)/'test'
    cpp.write_text(prefix+'\n'.join(functions)+harness)
    subprocess.run(['c++','-std=c++17','-fsanitize=undefined','-fno-sanitize-recover=all',str(cpp),'-o',str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    for args in ((8,1,0,4),(16,2,2,4),(16,1,0,0)):
        cpp.write_text(prefix+'void invalid(std::vector<uint8_t> audio_data) {\n'+source(*args)+'\n}')
        result=subprocess.run(['c++','-std=c++17','-c',str(cpp),'-o',str(binary)+'.o'],capture_output=True,text=True)
        assert result.returncode and 'static assertion failed' in result.stderr, result.stderr
print('PCM formats, sign extrema, channels, gates, partial frames and invalid settings passed')
