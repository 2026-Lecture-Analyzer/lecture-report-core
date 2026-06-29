"""STT(음성/영상 → transcript) — Step -1.

녹화 파일을 Gemini 오디오 네이티브로 전사·화자분리해, 기존 파이프라인 입력과 동일한
`<HH:MM:SS> 화자ID(hex): 텍스트` transcript txt 를 만든다. 이후 parse→merge→refine→analyze
는 그대로 재사용한다(최소 변경·최대 재사용).

핵심:
- 모델 호출은 transcribe_fn 주입(refine 의 generate_fn 패턴) → GPU·키·오디오 없이 smoke 검증.
- 긴 강의는 ffmpeg 로 STT_CHUNK_SEC 단위로 잘라 전사 후, 청크 시작초만큼 타임스탬프를 밀어
  이어붙인다(체크포인트/재개).
"""
