# GECO 플러그인 화이트리스트 (핸드크래프트용 작업 문서)

`fixtures/installed-effects.json`(라이브 mod-ui 덤프, 72개)에서 생성. 아래 버킷은 LV2 카테고리
기반 **자동 제안**일 뿐 — 직접 손보세요:

- **포함/제외:** `[x]`=GECO 화이트리스트 포함, `[ ]`=제외 (기타 이펙트와 무관한 신스·MIDI·CV 등은 빼면 됨)
- **재분류:** 줄을 다른 `## 버킷` 섹션으로 옮기면 됨
- **버킷 개편:** 섹션 헤더(`## ABBR — 이름`)의 약어·이름을 바꾸거나 섹션을 추가/삭제
- **순서:** 섹션·줄 순서 = GECO에서의 표시 순서

약어(ABBR)는 노드 스트립에 3글자로 뜬다(예: DRV). 다 정하면 나에게 주면 app.py의 화이트리스트로 변환함.

---

## DRV — Drive   (4)
- [ ] **Bitta** · OpenAV  · LV2:Distortion
- [ ] **bluesbreaker** · brummer  · LV2:Distortion
- [ ] **ChowCentaur** · chowdsp  · LV2:Distortion
- [ ] **GxColorSoundTonebender** · Guitarix  · LV2:Distortion

## CMP — Comp   (2)
- [ ] **GxCompressor** · Guitarix team  · LV2:Dynamics/Compressor
- [ ] **GxMultiBandCompressor** · Guitarix team  · LV2:Dynamics/Compressor

## GTE — Gate   (2)
- [ ] **abGate** · A. Bruzas  · LV2:Dynamics/Gate
- [ ] **GxSlowGear** · Guitarix  · LV2:Dynamics/Gate

## DYN — Dynamics   (3)
- [ ] **Compressor Advanced** · MOD  · LV2:Dynamics
- [ ] **GxExpander** · Guitarix team  · LV2:Dynamics/Expander
- [ ] **Harmonic Exciter** · brummer  · LV2:Dynamics

## EQ  — EQ   (1)
- [ ] **3 Band EQ** · DISTRHO  · LV2:Filter/Equaliser

## FLT — Filter   (6)
- [ ] **BandPassFilter** · MOD  · LV2:Filter
- [ ] **Capacitor2** · Hannes Braun  · LV2:Filter
- [ ] **CrossOver 2** · MOD  · LV2:Filter
- [ ] **CrossOver 3** · MOD  · LV2:Filter
- [ ] **GxQuack** · Guitarix  · LV2:Filter
- [ ] **mud** · remaincalm.org  · LV2:Filter

## MOD — Mod   (5)
- [ ] **C* PhaserII - Mono phaser modulated by a Lorenz fractal** · CAPS  · LV2:Modulator/Phaser
- [ ] **GxFlanger** · Guitarix team  · LV2:Modulator/Flanger
- [ ] **GxTremolo** · Guitarix team  · LV2:Modulator
- [ ] **GxTubeVibrato** · Guitarix team  · LV2:Modulator
- [ ] **the infamous power cut** · infamous  · LV2:Modulator

## DLY — Delay   (2)
- [ ] **Bollie Delay** · Bollie  · LV2:Delay
- [ ] **floaty** · remaincalm.org  · LV2:Delay

## RVB — Reverb   (10)
- [ ] **Aether** · Dougal Stewart  · LV2:Reverb
- [ ] **C* Plate - Versatile plate reverb** · CAPS  · LV2:Reverb
- [ ] **Convolution Loader** · MOD  · LV2:Reverb
- [ ] **Dragonfly Early Reflections** · Dragonfly  · LV2:Reverb
- [ ] **Dragonfly Hall Reverb** · Dragonfly  · LV2:Reverb
- [ ] **Dragonfly Plate Reverb** · Dragonfly  · LV2:Reverb
- [ ] **Dragonfly Room Reverb** · Dragonfly  · LV2:Reverb
- [ ] **StarChild** · Airwindows  · LV2:Reverb
- [ ] **x42 - IR Convolver Mono** · x42  · LV2:Reverb
- [ ] **x42 - IR Convolver Stereo** · x42  · LV2:Reverb

## PIT — Pitch   (6)
- [ ] **2Voices** · MOD  · LV2:Spectral
- [ ] **Autotune** · x42  · LV2:Spectral/Pitch Shifter
- [ ] **Capo** · MOD  · LV2:Spectral
- [ ] **Harmonizer** · MOD  · LV2:Spectral
- [ ] **MDA VocInput** · MDA  · LV2:Spectral
- [ ] **TAP Fractal Doubler** · TAP  · LV2:Spectral

## AMP — Amp·Cab   (5)
- [ ] **AIDA-X** · Aida DSP  · LV2:Simulator
- [ ] **Cabinet Loader** · MOD  · LV2:Simulator
- [ ] **GxRedeye Vibro Chump** · Guitarix  · LV2:Simulator
- [ ] **IR loader cabsim** · MOD  · LV2:Simulator
- [ ] **Neural Amp Modeler** · Mike Oliphant  · LV2:Simulator

## SYN — Synth   (7)
- [ ] **amsynth** · Dowell  · LV2:Generator/Instrument
- [ ] **DIE Fluid Synth** · DISTRHO  · LV2:Generator/Instrument
- [ ] **Fluid Guitars** · FluidGM  · LV2:Generator/Instrument
- [ ] **Fluid Organs** · FluidGM  · LV2:Generator/Instrument
- [ ] **Fluid SynthLeads** · FluidGM  · LV2:Generator/Instrument
- [ ] **Kars** · DISTRHO  · LV2:Generator/Instrument
- [ ] **Nekobi** · DISTRHO  · LV2:Generator/Instrument

## SPA — Spatial   (2)
- [ ] **C* Wider - Stereo image Synthesis** · CAPS  · LV2:Spatial
- [ ] **MDA Stereo** · MDA  · LV2:Spatial

## UTL — Utility   (14)
- [ ] **ADClip7** · Hannes Braun  · LV2:(none)
- [ ] **ALO**  · LV2:Utility
- [ ] **Audio File** · falkTX  · LV2:Utility
- [ ] **C* Click - Metronome** · CAPS  · LV2:Utility
- [ ] **C* Noisegate - Attenuate noise resident in silence** · CAPS  · LV2:Utility
- [ ] **Gain** · MOD  · LV2:Utility
- [ ] **Gain 2x2** · MOD  · LV2:Utility
- [ ] **Instrument Tuner** · x42  · LV2:Utility/Analyser
- [ ] **Level Meter** · x42  · LV2:Utility
- [ ] **MIDI File** · falkTX  · LV2:Utility
- [ ] **Record-Mono** · brummer  · LV2:Utility
- [ ] **Record-Quad** · brummer  · LV2:Utility
- [ ] **Record-Stereo** · brummer  · LV2:Utility
- [ ] **Spectrum Analyzer** · x42  · LV2:Utility

## CV  — CV   (2)
- [ ] **Audio to CV** · MOD  · LV2:ControlVoltage
- [ ] **AudioToCV Pitch** · MOD/DISTRHO  · LV2:ControlVoltage

## MID — MIDI   (1)
- [ ] **MIDI Step Sequencer8x8** · x42  · LV2:MIDI
