import os

#MODEP controls

SERVER_URI         = "http://localhost/"
LOCAL_STORAGE      = os.path.expanduser("~/.modep/")
LAST_PEDALBOARD    = LOCAL_STORAGE + "last_board"
DEFAULT_PEDALBOARD = "/var/modep/pedalboards/default.pedalboard"
DEFAULT_BANK       = 0


#APP configs
DEFAULT_USER_FILES_DIR = '/var/modep/user-files/'
PATCH_FILE_DIR_MAP = {
    "http://aidadsp.cc/plugins/aidadsp-bundle/rt-neural-generic#json": "/var/modep/user-files/Aida DSP Models/",
    "http://gareus.org/oss/lv2/zeroconvolv#ir": "/var/modep/user-files/Reverb IRs/",
    "http://moddevices.com/plugins/mod-devel/cabsim-IR-loader#ir": "/var/modep/user-files/Speaker Cabinets IRs/",
    "https://mod.audio/plugins/CabinetLoader#irfile": "/var/modep/user-files/Speaker Cabinets IRs/",
    "http://github.com/mikeoliphant/neural-amp-modeler-lv2#model": "/var/modep/user-files/NAM Models/",
    "defaultpath": "/var/modep/user-files/"
                        }
# mod-ui의 patch fileTypes는 확장자가 아니라 **논리적 카테고리명**('nammodel',
# 'cabsim' 등). 우리가 쓰는 카테고리만 실제 확장자로 매핑한다. 매핑에 없는
# 카테고리는 필터링하지 않음 → PATCH_FILE_DIR_MAP 디렉터리가 이미 타입별로
# 분리돼 있어 디렉터리 자체가 필터 역할을 한다(NAM Models=.nam, IRs=.wav…).
PATCH_FILE_TYPE_EXTS = {
    "nammodel":     [".nam"],
    "aidadspmodel": [".aidax", ".json"],
    "cabsim":       [".wav"],
    "ir":           [".wav"],
    "audio":        [".wav", ".flac", ".aiff", ".aif"],
    "sf2":          [".sf2", ".sf3"],
    "sfz":          [".sfz"],
    "h2drumkit":    [".h2drumkit"],
}
SCALE_FACTOR = 4
PLG_MAX_CHARACTERS = 12
PRM_MAX_CHARACTERS = 10
FONT_DIR = './resources/fonts'
FONTS = [os.path.join(FONT_DIR, font_name) for font_name in [
    'GalmuriMono7.ttf', 'mago1.ttf', 'mago2.ttf',
    'mago3.ttf', 'monogram.ttf', 'ThaleahFat.ttf'
]]
SOCKET_PATH = "/tmp/synapsin.sock"
