"""Use Home Assistant's real blueprint/automation schemas, templates and scripts."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import unquote

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA, async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.helpers.script import Script
from homeassistant.helpers.script_variables import ScriptVariables
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
COMMON = dict(measurement_active='binary_sensor.measurement', last_sample='sensor.last_sample',
              ignored_appliances=['switch.extractor'], ignored_players=['media_player.tv'])

async def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        hass.config_entries = ConfigEntries(hass, {})
        assert await async_setup_component(hass, 'automation', {'automation': []})
        await trigger_helper.async_setup(hass)
        hass.config.time_zone = 'UTC'
        dt_util.set_default_time_zone(timezone.utc)
        configs = {}
        for path in sorted((ROOT/'blueprints/automation').glob('*.yaml')):
            data = load_yaml(str(path))
            bp = Blueprint(data, path=path.name, expected_domain='automation', schema=AUTOMATION_BLUEPRINT_SCHEMA)
            assert not bp.validate(), bp.validate()
            inputs = {**COMMON}
            if 'sound_sensor' in bp.inputs: inputs['sound_sensor']='sensor.sound_detection'
            if 'people' in bp.inputs: inputs['people']=['person.alice','person.bob']
            if 'sound_level' in bp.inputs: inputs.update(sound_level='sensor.sound_level',start_time='00:00:00',end_time='00:00:00')
            if 'activity_helper' in bp.inputs: inputs.update(activity_helper='input_boolean.recent_sound',hold_timer='timer.recent_sound')
            instance=BlueprintInputs(bp,{'use_blueprint':{'path':path.name,'input':inputs}})
            instance.validate()
            raw=instance.async_substitute()
            validated=await async_validate_config_item(hass,'automation',raw)
            assert validated is not None,path
            # Test every referenced trigger/action schema with actual substituted inputs.
            configs[path.stem]={**raw, 'actions': validated['actions'], 'validated_variables': validated['variables']}
            readme=unquote((ROOT/'README.md').read_text())
            assert data['blueprint']['source_url'] in readme,path

        def set_state(entity,state,attrs=None): hass.states.async_set(entity,str(state),attrs or {})
        def reset():
            for entity,state in [('binary_sensor.measurement','on'),('sensor.last_sample',NOW.isoformat()),
                ('switch.extractor','off'),('media_player.tv','idle'),('sensor.sound_detection','presence'),
                ('sensor.sound_level','70'),('person.alice','not_home'),('person.bob','work'),
                ('input_boolean.recent_sound','off'),('timer.recent_sound','idle')]: set_state(entity,state)
        def render(value,variables):
            return Template(value,hass).async_render(variables,parse_result=True)
        def qualifies(config,variables=None):
            trigger=next(t for t in config['triggers'] if t['trigger']=='template')
            return render(trigger['value_template'],variables or config['trigger_variables'])

        with patch.object(dt_util,'now',return_value=NOW),patch.object(dt_util,'utcnow',return_value=NOW):
            for name,config in configs.items():
                reset();assert qualifies(config),name
                for entity,state in [('binary_sensor.measurement','off'),('binary_sensor.measurement','unavailable'),
                    ('sensor.last_sample','unknown'),('switch.extractor','on'),('switch.extractor','unavailable'),
                    ('media_player.tv','playing'),('media_player.tv','buffering'),('media_player.tv','unknown')]:
                    reset();set_state(entity,state);assert not qualifies(config),(name,entity,state)
                reset();set_state('sensor.last_sample',(NOW-timedelta(seconds=11)).isoformat());assert not qualifies(config),name
                reset();set_state('sensor.last_sample',(NOW+timedelta(seconds=10)).isoformat());assert not qualifies(config),name
                reset()
            away=configs['unexpected_sound_while_away']
            for state in ['home','unknown','unavailable']:
                reset();set_state('person.bob',state);assert not qualifies(away),state
            reset();assert not qualifies(away,{**away['trigger_variables'],'people':[]})
            set_state('sensor.sound_detection','silence');assert not qualifies(away)
            set_state('sensor.sound_detection','quieting');assert not qualifies(away)
            noise=configs['sustained_noise_reminder'];reset()
            for state in ['unknown','unavailable','55','54']:
                set_state('sensor.sound_level',state);assert not qualifies(noise),state
            reset();v={**noise['trigger_variables'],'start_time':'22:00:00','end_time':'06:00:00'}
            assert not qualifies(noise,v)
            with patch.object(dt_util,'now',return_value=NOW.replace(hour=23)):
                set_state('sensor.last_sample',NOW.replace(hour=23).isoformat());assert qualifies(noise,v)
            for name in ['unexpected_sound_while_away','sustained_noise_reminder']:
                c=configs[name]['conditions'][0]['value_template']
                assert render(c,{'this':{'attributes':{}},'cooldown_minutes':30})
                assert not render(c,{'this':{'attributes':{'last_triggered':NOW-timedelta(minutes=5)}},'cooldown_minutes':30})
                assert render(c,{'this':{'attributes':{'last_triggered':NOW-timedelta(minutes=31)}},'cooldown_minutes':30})

            # Run the real helper action sequence against recorded, isolated services.
            calls=[]
            async def service(call):
                calls.append((call.domain,call.service))
                entity=call.data['entity_id'];entity=entity[0] if isinstance(entity,list) else entity
                set_state(entity,('active' if call.service=='start' else 'idle') if call.domain=='timer' else ('on' if call.service=='turn_on' else 'off'))
            for domain,names in [('input_boolean',['turn_on','turn_off']),('timer',['start','cancel'])]:
                for name in names: hass.services.async_register(domain,name,service)
            helper=configs['recent_sound_activity']
            async def run(trigger):
                await hass.async_block_till_done()
                values={**helper['trigger_variables'],'trigger':{'id':trigger}}
                values=helper['validated_variables'].async_render(hass,values)
                script=Script(hass,helper['actions'],'SoundSense test','soundsense')
                await script.async_run(values, context=Context())
            reset();await run('qualified')
            assert hass.states.is_state('input_boolean.recent_sound','on') and hass.states.is_state('timer.recent_sound','active')
            calls.clear();await run('refresh');assert ('timer','start') in calls
            set_state('binary_sensor.measurement','off');calls.clear();await run('refresh');assert not calls
            set_state('timer.recent_sound','idle');await run('expiry');assert hass.states.is_state('input_boolean.recent_sound','off')
            reset();await run('qualified');calls.clear();await run('startup')
            assert hass.states.is_state('input_boolean.recent_sound','off') and hass.states.is_state('timer.recent_sound','idle')
            assert ('timer','cancel') in calls
        await hass.async_stop()
    print('Three real HA blueprint/automation schemas, freshness/exclusions/away/hours/cooldown templates and helper lifecycle actions passed')

asyncio.run(main())
