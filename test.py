import subprocess
import time


import subprocess
import time

def toggle_wvkbd(onlykill=False):
    print('hello, i am toggling wvkbd')
    # Capture the output of `pidof wvkbd-mobintl`
    result = subprocess.run(["pidof", "wvkbd-mobintl"], capture_output=True, text=True)
    pid = result.stdout.strip()

    if pid:
        # If a PID is found, kill all running instances of wvkbd-mobintl
        subprocess.run(["killall", "wvkbd-mobintl"])
    else:
        if onlykill:
            return

        # Launch the new instance asynchronously so it doesn't block
        subprocess.Popen([
            "wvkbd-mobintl",
            "-L", "120",
            "-fg", "ffffff",
            "-fg-sp", "ffffff",
            "--text", "000000",
            "--text-sp", "000000",
            "-fn", "12"
        ])

if __name__ == '__main__':
    toggle_wvkbd()
    time.sleep(1)  # Optional delay before toggling off
    toggle_wvkbd()
