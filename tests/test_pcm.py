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
#include <cassert>
#include <cmath>
#include <cstdint>
#include <vector>
float current_sound_level = -1;
bool idle = true, allowed = true;
#define id(x) x
'''
functions = []
for bits in (16, 24, 32):
    for channels, channel in ((1, 0), (2, 0), (2, 1)):
        name = f'pcm_{bits}_{channels}_{channel}'
        functions.append(f'void {name}(std::vector<uint8_t> audio_data) {{\n{source(bits, channels, channel)}\n}}')
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
harness += '}\n'
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
