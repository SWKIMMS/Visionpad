"""Run an isolated browser check on port 8001; the normal game's progress is untouched."""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import uvicorn
from fastapi.responses import HTMLResponse
import game_app
from game_engine import GameEngine
from tools.audio_flow import fixture_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--scene',choices=('water','mine','npc'),default='water')
    args=parser.parse_args()
    if args.port==8000:
        parser.error('Port 8000 is reserved for the normal game; use a separate port.')
    with tempfile.TemporaryDirectory(prefix='visionpad-audio-browser-') as saved:
        engine=GameEngine(fixture_config(),save_dir=saved)
        if args.scene=='mine':
            engine.resources['pickaxe']=1
            engine.travel_to('mine')
        else:
            engine.travel_to('farm')
            plot=engine.get_unlocked_plot_defs()[0]['id']
            engine.plant_seed(plot,'tomato')
            if args.scene=='water':
                engine.start_care_minigame(plot,'water')
            else:
                # A mature fixture lets the real harvest input produce the reaction.
                engine.farm_plots[plot]['mature']=True
                engine.start_harvest_minigame(plot)
                targets=list(engine.harvest_targets)
                engine.pointer_down(targets[0]['x'],targets[0]['y'])
                for target in targets[1:]:
                    engine.pointer_drag(target['x'],target['y'])
                engine.pointer_up(targets[-1]['x'],targets[-1]['y'])
                engine.travel_to('town')
        game_app.engine=engine

        @game_app.app.middleware('http')
        async def label_test_progress(request,call_next):
            if request.url.path=='/':
                text=(ROOT/'web/game.html').read_text()
                text=text.replace('>Tactile garden<','>INTEGRATION TEST · SEPARATE PROGRESS<')
                text=text.replace('<title>Dotdew Valley · Tactile garden</title>',
                    '<title>Dotdew Valley · Separate audio test</title>')
                return HTMLResponse(text)
            return await call_next(request)

        uvicorn.run(game_app.app,host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':
    main()
