# 사운드·영어 음성·Rowan 전달 안내

2026-10-18 기준. 팀 저장소 `seojbin/Visionpad`의 `main` 커밋 `3728f76`에 사운드 작업을 통합했다. 작업 브랜치는 [SWKIMMS/Visionpad · codex/audio-tts-npc](https://github.com/SWKIMMS/Visionpad/tree/codex/audio-tts-npc)다. 원본 저장소에는 PR을 통해 반영한다.

## 추가한 기능

| 기능 | 동작 | 주요 파일 |
|---|---|---|
| 일정한 영어 음성 | Piper의 고정 시스템/Rowan 목소리, 발음 보정, WAV 캐시 | `game_speech.py`, `speech_config.json` |
| 음성 재생 | 다시 듣기·중지·음소거·속도·별도 음량 85%, 늦은 안내 취소 | `web/game-speech.js`, `game_app.py`, `speech_queue.py` |
| 퀘스트 안내 | 팀 Rowan 튜토리얼을 같은 목소리로 읽고, 다른 행동 안내는 대사가 끝날 때까지 보류 | `game_npc.py`, `web/game-speech.js` |
| Rowan 조언 | **상점 → Ask Rowan for advice → Farming / Fishing / Open shop / Goodbye** | `game_npc.py`, `npc_config.json` |
| 최근 행동 반응 | 실제 수확·요리·낚시·채굴·도구 파괴를 다음 대화에 한 번 반영, 저장/로드 지원 | `game_npc.py`, `game_saves.py` |
| 효과음 | 작업·목표 통과·전체 완료·실패 구분, 중복/이전 화면 소리 방지, 음원 실패 후 재시도 | `web/game-audio.js`, 엔진의 `sound_events` |
| 목표 안내 | 물·비료·수확·광산의 남은 목표를 HRTF 방향음으로 안내, 거리/진행에 따른 변화 | `GameEngine.audio_guidance`, `web/game-audio.js` |
| 준비/실행 | 프로젝트 가상환경·모델 설치, 실제 음성 생성 점검, 기존 게임 재사용, 시연 음성 준비 | `setup-*`, `launch_game.py`, `tools/` |

원본 MP3 18개와 낚시 HRTF는 유지한다. 최신 팀 코드의 작업음 위치 처리, 게임 음량 기본 90%, 이동만으로 수행하는 농사·요리, F4 선택, 아이콘/날짜/요일별 거래와 Rowan 퀘스트도 보존한다. 원본 퀘스트의 수프·씨앗·100골드 보상을 조언 기능에서 중복 지급하지 않는다. 조언만 듣거나 Replay를 눌러도 게임 시간·재화는 소비하지 않는다.

## 팀원이 실행하는 방법

1. 이 작업 브랜치 전체를 받는다. PR 병합 전의 팀 `main`에는 새 음성 모듈이 없다.
2. Python 3.11 이상을 준비하고 Mac에서는 `setup-mac.command`, Windows에서는 `setup-windows.bat`를 실행한다. 최초 패키지/모델 다운로드에는 인터넷이 필요하다. API 키는 필요 없다.
3. Mac은 `start-mac.command`(8000), Windows는 `game.bat`(8003)를 실행한다. 웹 파일 교체 후 게임과 시각화 창을 새로고침한다.
4. **Test guide / Test Rowan**으로 음성을 확인한다. **Speech volume**은 목소리, **Sound volume**은 게임 소리를 조절한다.
5. 마을 Rowan의 퀘스트와 상점의 조언을 각각 확인한다. 농사·광산에서는 **Target cues on/off**로 새 목표음을 비교한다. 현재 평가 버전에서 F4는 **선택**이다.

설치 문제는 [SETUP.md](SETUP.md), 시연용 캐시는 [DEMO_READY.md](DEMO_READY.md), 실제 청취는 [LISTENING_CHECK.md](LISTENING_CHECK.md)를 따른다.

## 검증과 범위

```bash
python -m unittest test_team_audio test_speech_queue test_speech_api test_gameplay_audio test_speech test_fishing test_sound_events test_audio_flow test_demo_speech test_startup -q
node --test test_speech.cjs test_guidance.cjs test_fishing_audio.cjs test_effects.cjs test_audio_integration.cjs test_hardware.mjs
python tools/check_setup.py --synthesize
```

현재 Mac arm64/Python 3.14.3에서 Python **75개**, Node **72개**, 총 **147개**를 확인한다. 퀘스트 보상 중복 방지, 기존 저장의 퀘스트 단계 보존, 조언의 무소비 동작, 움직임만으로 수행하는 작업과 위치음, 퀘스트 대사 보호를 포함한다. 두 목소리의 실제 WAV 생성과 환경 점검 13개도 통과했다. 시연 음성 203/203개를 준비했고 이번 실행에서는 171개 재사용, 32개 신규 생성이었다.

별도 8001번 임시 게임에서 실제 수확 후 Rowan 퀘스트 반응·수프 사용·상점 조언·다시 듣기를 확인했다. 브라우저 경고/오류는 없었다. 테스트는 임시 저장을 쓰며 기존 플레이 저장을 불러오거나 변경하지 않는다. 전체 디렉터리의 일반 unittest discovery는 별도 카메라 모듈 `tracking`도 가져와 OpenCV를 요구하므로 위의 게임용 검사 명령을 사용한다. 카메라 모듈을 이 검증에 포함한 것은 아니다.

Windows/다른 PC의 실제 설치, 실물 Dot Pad·카메라 연결, 새 목표음의 세부 앞뒤 지각과 혼합 균형은 추가 확인 대상이다. 기존의 초기 청취 피드백을 새 기능의 전체 청취 검증으로 취급하지 않는다.

## 저장소에 포함하지 않는 파일

음성 모델(`models/`), 생성 WAV(`.cache/speech/`), 실제 저장(`saves/`), 테스트 출력(`output/`), 가상환경과 개인 작업 메모는 Git에서 제외한다. 팀원이 자신의 PC에서 설치/준비 도구로 생성한다. 모델 출처와 라이선스 링크는 [SOUND_MAP.md](SOUND_MAP.md)에 있다.

코드 설명은 [GAMEPLAY_UPDATE.md](GAMEPLAY_UPDATE.md), 초기 효과음 통합 검증 기록은 [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md)를 참고한다.
