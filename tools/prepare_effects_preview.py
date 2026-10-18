"""Build a labelled effects listening reel. Requires FFmpeg and Node, not a game session."""
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_speech import SpeechService

RATE = 22050


def pcm(path, seconds=None):
    command = ['ffmpeg','-v','error','-i',str(path)]
    if seconds is not None:
        command += ['-t',str(seconds)]
    command += ['-f','f32le','-ac','1','-ar',str(RATE),'-']
    return np.frombuffer(subprocess.check_output(command),dtype='<f4').copy()


def render_cue(notes):
    output = np.zeros(int((max(offset+duration for _,offset,duration,_ in notes)+0.03)*RATE))
    for frequency,offset,duration,level in notes:
        time = np.arange(int(duration*RATE))/RATE
        attack = 0.008
        envelope = np.where(time<attack,0.0001+(level-0.0001)*time/attack,
            level*(0.0001/level)**np.clip((time-attack)/(duration-attack),0,1))
        note = np.sin(2*np.pi*frequency*time)*envelope
        start = int((offset+0.005)*RATE)
        output[start:start+len(note)] += note
    return output


def main():
    settings = json.loads((ROOT/'game_config.json').read_text())['interaction']['audio']
    cues = json.loads(subprocess.check_output(['node','-e',
        "process.stdout.write(JSON.stringify(require('./web/game-audio.js').SOUND_CUES))"],cwd=ROOT))
    speech = SpeechService(ROOT)
    output_dir = ROOT/'output'/'audio'
    output_dir.mkdir(parents=True,exist_ok=True)
    examples = [('Watering','water','work',1.5),('Fertilizing','soil','work',1.5),
        ('Harvesting','crop','work',None),('Chopping','cut','work',None),('Cooking','cook','work',1.5),
        ('Walking','step','effect',None),('Shop door','door','effect',None),('Transaction','coin','effect',None),
        ('Pickaxe','pickaxe','effect',None),('Rock breaking','break','effect',None),
        ('Rare reward','shine','effect',2.8),('Fish caught','splash','effect',1.8),
        ('Planting','plant','cue',None),('Task complete','complete','cue',None),
        ('Action unavailable','error','cue',None),('No catch','miss','cue',None)]
    clips=[]
    manifest=[]
    cursor=0
    silence=np.zeros(int(RATE*0.25))
    for label,name,kind,seconds in examples:
        voice = speech.generate(label+'.')
        announcement = pcm(speech.audio_path(voice['key']))*0.75
        if kind == 'cue':
            effect = render_cue(cues[name])
        else:
            effect = pcm(ROOT/'web'/'audio'/(name+'.mp3'),seconds)
            gain = settings['work_gain'][name] if kind=='work' else settings['one_shot_gain'][settings.get('one_shot_gain_links',{}).get(name,name)]
            effect *= gain
        effect *= settings['default_volume']
        clips += [announcement,silence,effect,silence]
        manifest.append({'label':label,'effect':name,'starts_at_seconds':round(cursor/RATE,2)})
        cursor += len(announcement)+len(effect)+2*len(silence)
    output = np.concatenate(clips)
    peak = float(np.max(np.abs(output)))
    if peak >= 1:
        raise ValueError(f'Preview peak would clip: {peak:.3f}')
    target = output_dir/'effects-preview.wav'
    with wave.open(str(target),'wb') as destination:
        destination.setnchannels(1); destination.setsampwidth(2); destination.setframerate(RATE)
        destination.writeframes((output*32767).astype('<i2').tobytes())
    (output_dir/'effects-preview.json').write_text(json.dumps({'seconds':round(len(output)/RATE,2),
        'peak':round(peak,4),'note':'Mono listening reel; does not reproduce fishing HRTF or live mixing.',
        'examples':manifest},indent=2)+'\n')
    print(f'Ready: {target.relative_to(ROOT)} ({len(output)/RATE:.1f}s, peak {peak:.3f})')


if __name__ == '__main__':
    main()
