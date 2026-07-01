import mido
import time
import utils
from hardwares.ADS1115 import ADS1115

# Initialize ADS1115
ADS = ADS1115(1, 0x49)
ADS.setGain(ADS.PGA_4_096V)  # FSR +-4.096V: 25K TRS 분배기 상단(~2.36V)이 2.048V를 넘어 클리핑되는 것 방지
ADS.setDataRate(ADS.DR_128SPS)  # 페달엔 860SPS가 과함. 느릴수록 내부평균으로 노이즈↓·입력임피던스↑ (50ms 루프에 7.8ms 변환은 여유)

# Find the "GAAD67" MIDI port
midi_port_name = "GAAD67"
available_ports = mido.get_output_names()

# Try to find the correct port even if it has additional characters
matching_ports = [port for port in available_ports if midi_port_name in port]

if not matching_ports:
    print(f"ERROR: MIDI port '{midi_port_name}' not found. Available ports: {available_ports}")
    exit(1)

# Open the first matching port
midiout = mido.open_output(matching_ports[0])
print(f"Connected to MIDI port: {matching_ports[0]}")

# MIDI CC Numbers
CC_VOLUME = 7  # Master Volume
CC_EXPR = 11  # Expression

# 채널별 보정(in_min/in_max)은 ~/.modep/pedal_calibration.json에 별도 저장 →
# 채널마다 다른 페달 모델을 꽂아도 코드 수정 없이 값만 갱신하면 됨.
# 실측(힐~토 홀드, ±4.096V FSR): 밟음(토)~17940, 뗌(힐)~0. 파일 없으면 utils의 기본값 사용.
CAL = utils.load_pedal_calibration()


def map_value(value, in_min=150, in_max=17700, out_min=0, out_max=127):
    """Maps 16-bit ADS1115 range to 7-bit MIDI CC range with dead zones."""
    if value < in_min:
        return out_min
    elif value > in_max:
        return out_max
    return int((value - in_min) / (in_max - in_min) * (out_max - out_min) + out_min)


# Time to ignore MIDI outputs after startup (in seconds)
ignore_duration = 3
start_time = time.time()

# Initialize previous values (None means no previous value yet)
prev_midi_vol = None
prev_midi_expr = None

try:
    while True:
        current_time = time.time()

        # Read ADS1115 values
        ads_0 = ADS.readChannel(0)  # Volume Control
        ads_1 = ADS.readChannel(1)  # Expression Pedal

        # Map to MIDI range (0-127) using per-channel calibration
        midi_vol = map_value(ads_0, **CAL[0])   # ch0 = Volume
        midi_expr = map_value(ads_1, **CAL[1])  # ch1 = Expression

        if current_time - start_time < ignore_duration:
            # During the ignore period, update the previous values without sending MIDI messages.
            prev_midi_vol = midi_vol
            prev_midi_expr = midi_expr
        else:
            # Send a MIDI message only if the volume value has changed.
            if midi_vol != prev_midi_vol:
                midiout.send(mido.Message('control_change', channel=0, control=CC_VOLUME, value=midi_vol))
                prev_midi_vol = midi_vol
                print(f"Sent MIDI (if changed): Volume={midi_vol}, Expression={midi_expr}")

            # Send a MIDI message only if the expression value has changed.
            if midi_expr != prev_midi_expr:
                midiout.send(mido.Message('control_change', channel=0, control=CC_EXPR, value=midi_expr))
                prev_midi_expr = midi_expr
                print(f"Sent MIDI (if changed): Volume={midi_vol}, Expression={midi_expr}")

        time.sleep(0.05)  # Poll every 50ms

except KeyboardInterrupt:
    print("Stopping MIDI control...")
    midiout.close()
