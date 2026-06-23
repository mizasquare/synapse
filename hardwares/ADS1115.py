# ads1115_minimal.py
from hardwares.Adafruit_I2C import Adafruit_I2C
import time

class ADS1115:
    """
    Minimal ADS1115 driver using the Adafruit_I2C wrapper.
    Provides:
      - Single-ended reads from A0..A3
      - Differential reads from (0-1, 0-3, 1-3, 2-3) if needed
      - Basic PGA (gain), data rate, and comparator config

    Note: This code is intentionally stripped down to only support ADS1115.
    """

    #----- Register addresses -----
    CONVERSION_REG = 0x00
    CONFIG_REG     = 0x01
    LO_THRESH_REG  = 0x02
    HI_THRESH_REG  = 0x03

    #----- Multiplexer config constants (bits 12-14 in config) -----
    MUX_DIFF_0_1 = 0b000  # Differential P=AIN0, N=AIN1
    MUX_DIFF_0_3 = 0b001  # Differential P=AIN0, N=AIN3
    MUX_DIFF_1_3 = 0b010  # Differential P=AIN1, N=AIN3
    MUX_DIFF_2_3 = 0b011  # Differential P=AIN2, N=AIN3
    MUX_SINGLE_0 = 0b100  # Single-ended AIN0
    MUX_SINGLE_1 = 0b101  # Single-ended AIN1
    MUX_SINGLE_2 = 0b110  # Single-ended AIN2
    MUX_SINGLE_3 = 0b111  # Single-ended AIN3

    #----- PGA config constants (bits 9-11 in config) -----
    PGA_6_144V = 0x0000  # ±6.144 V
    PGA_4_096V = 0x0200  # ±4.096 V
    PGA_2_048V = 0x0400  # ±2.048 V
    PGA_1_024V = 0x0600  # ±1.024 V
    PGA_0_512V = 0x0800  # ±0.512 V
    PGA_0_256V = 0x0A00  # ±0.256 V

    #----- Mode config constants (bit 8 in config) -----
    MODE_CONTINUOUS = 0
    MODE_SINGLE     = 0x0100

    #----- Data Rate constants (bits 5-7 in config), ADS1115 only -----
    DR_8SPS   = 0x0000
    DR_16SPS  = 0x0020
    DR_32SPS  = 0x0040
    DR_64SPS  = 0x0060
    DR_128SPS = 0x0080  # default
    DR_250SPS = 0x00A0
    DR_475SPS = 0x00C0
    DR_860SPS = 0x00E0

    #----- Comparator config (bits 0-4, for advanced usage) -----
    COMP_MODE_TRAD = 0x0000  # Traditional comparator
    COMP_MODE_WINDOW = 0x0010
    COMP_POL_ACTIVE_LOW  = 0x0000
    COMP_POL_ACTIVE_HIGH = 0x0008
    COMP_LAT_NONLATCHING = 0x0000
    COMP_LAT_LATCHING    = 0x0004
    COMP_QUE_ASSERT1     = 0x0000  # Assert after 1 conversion
    COMP_QUE_ASSERT2     = 0x0001  # Assert after 2 conversions
    COMP_QUE_ASSERT4     = 0x0002  # Assert after 4 conversions
    COMP_QUE_DISABLE     = 0x0003  # Disable comparator (most common)

    _DATA_RATE_TO_DELAY_MS = {
        0x0000: 125.0,  # 8 SPS
        0x0020: 62.5,  # 16 SPS
        0x0040: 31.25,  # 32 SPS
        0x0060: 15.625,  # 64 SPS
        0x0080: 7.8125,  # 128 SPS
        0x00A0: 4.0,  # 250 SPS
        0x00C0: 2.105,  # 475 SPS
        0x00E0: 1.5,  # 860 SPS (datasheet says ~1.12 ms, you can fine-tune)
    }

    def __init__(self, busnum=1, address=0x48, debug=False):
        """
        Minimal constructor. Creates the I2C instance and sets up default config.
        Default config: Single-shot mode, ±2.048 V range, 128 SPS, single-ended AIN0.
        """
        self.i2c = Adafruit_I2C(address, busnum=busnum, debug=debug)
        self.address = address
        # 16-bit device
        self._adcBits = 16
        # Delay in ms to wait for single-shot conversion at default 128 SPS
        self._conversionDelay = 8

        # Build a default config value:
        #  Bits: OS=1 (in case revert to start single-shot), MUX=AIN0, PGA=±2.048, MODE=continuous
        #  DR=128SPS, COMP_MODE=traditional, COMP_POL=low, COMP_LAT=non-latching, COMP_QUE=disabled
        self._config = 0x8000 | (self.MUX_SINGLE_0 << 12) | self.PGA_2_048V | self.MODE_SINGLE \
                       | self.DR_128SPS | self.COMP_MODE_TRAD | self.COMP_POL_ACTIVE_LOW \
                       | self.COMP_LAT_NONLATCHING | self.COMP_QUE_DISABLE

        # Write default config to device
        self._writeRegister(self.CONFIG_REG, self._config)

    #--------------------------------------------------------------------------
    # I2C read/write helpers
    #--------------------------------------------------------------------------
    def _writeRegister(self, reg, value):
        """Write a 16-bit integer to the given register."""
        high = (value >> 8) & 0xFF
        low  = value & 0xFF
        self.i2c.writeList(reg, [high, low])

    def _readRegister(self, reg):
        """Read a 16-bit integer from the given register."""
        data = self.i2c.readList(reg, 2)
        return (data[0] << 8) | data[1]

    #--------------------------------------------------------------------------
    # Basic Config Getters/Setters
    #--------------------------------------------------------------------------
    def setGain(self, gain):
        """Set programmable gain amplifier (PGA) range."""
        # Clear bits 9..11, then OR in new gain bits
        self._config = (self._config & 0xF1FF) | gain
        self._writeRegister(self.CONFIG_REG, self._config)

    def getGain(self):
        """Return the current gain setting (one of the PGA_ constants)."""
        return self._config & 0x0E00

    def setDataRate(self, dataRate):
        """Set data rate (samples per second) and automatically adjust single-shot delay."""
        # Clear bits 5..7, then OR in new data rate
        self._config = (self._config & 0xFF1F) | dataRate
        self._writeRegister(self.CONFIG_REG, self._config)

        # Update the conversion delay for single-shot usage (in ms)
        if dataRate in self._DATA_RATE_TO_DELAY_MS:
            self._conversionDelay = self._DATA_RATE_TO_DELAY_MS[dataRate]
        else:
            # Fallback if unrecognized data rate
            self._conversionDelay = 8.0

    def getDataRate(self):
        """Return current data rate (one of the DR_ constants)."""
        return self._config & 0x00E0

    def setModeContinuous(self):
        """Switch to continuous-conversion mode."""
        # Clear bit 8
        self._config = self._config & ~0x0100
        self._writeRegister(self.CONFIG_REG, self._config)

    def setModeSingleShot(self):
        """Switch to single-shot mode."""
        # Set bit 8
        self._config = self._config | 0x0100
        self._writeRegister(self.CONFIG_REG, self._config)

    def getMode(self):
        """Return 0 for continuous, 1 for single-shot."""
        return (self._config >> 8) & 1

    #--------------------------------------------------------------------------
    # Reading from the ADC
    #--------------------------------------------------------------------------
    def readChannel(self, channel):
        """
        Perform a single-shot read on a single-ended channel (0..3).
        Returns a signed integer representing the measured voltage vs. ground.
        """
        if channel < 0 or channel > 3:
            return 0  # out of range
        # MUX single ended bits: channel + 0b100
        mux = (channel + 4) << 12
        # Clear bits 12..14, then OR in the new mux
        self._config = (self._config & 0x8FFF) | mux

        # Set the OS bit (bit 15) if in single-shot mode to begin conversion
        if self.getMode() == 1:  # single-shot
            self._config |= 0x8000

        self._writeRegister(self.CONFIG_REG, self._config)

        # Wait for conversion if single-shot
        if self.getMode() == 1:
            time.sleep(self._conversionDelay / 1000.0)  # e.g. 8 ms at 128SPS
            # Alternatively, poll the OS bit in the config register until it’s ready.

        return self._getConversionResult()

    def readDifferential_0_1(self):
        """Perform a single-shot read of the differential between channels 0 and 1."""
        # MUX=000 (bits 12..14)
        mux = self.MUX_DIFF_0_1 << 12
        self._startSingleShot(mux)
        return self._getConversionResult()

    def readDifferential_0_3(self):
        mux = self.MUX_DIFF_0_3 << 12
        self._startSingleShot(mux)
        return self._getConversionResult()

    def readDifferential_1_3(self):
        mux = self.MUX_DIFF_1_3 << 12
        self._startSingleShot(mux)
        return self._getConversionResult()

    def readDifferential_2_3(self):
        mux = self.MUX_DIFF_2_3 << 12
        self._startSingleShot(mux)
        return self._getConversionResult()

    def _startSingleShot(self, muxValue):
        """Helper: set MUX in single-shot mode and trigger a conversion."""
        # Clear bits 12..14, set the new mux
        self._config = (self._config & 0x8FFF) | muxValue
        # If single-shot mode, set OS bit to start
        if self.getMode() == 1:
            self._config |= 0x8000
        self._writeRegister(self.CONFIG_REG, self._config)
        # Wait for the conversion
        if self.getMode() == 1:
            time.sleep(self._conversionDelay / 1000.0)

    def _getConversionResult(self):
        """Reads the 16-bit conversion register, shifts if needed, and returns signed int."""
        value = self._readRegister(self.CONVERSION_REG)
        # For ADS1115 (16-bit) no extra shifting needed; just handle sign.
        if value & 0x8000:  # negative in two's complement
            value -= 1 << 16
        return value

    #--------------------------------------------------------------------------
    # Helper for scaling to voltage
    #--------------------------------------------------------------------------
    def getVoltage(self, rawValue=None):
        """
        Convert a raw ADC reading to voltage based on the current PGA setting.
        If rawValue is None, automatically reads single-ended channel 0.
        """
        if rawValue is None:
            rawValue = self.readChannel(0)
        maxVoltage = self._lookupRangeVolts()
        # The ADS1115 is 16-bit, so the range is -32768..32767
        # But in single-ended mode, you’d typically get 0..+32767 for normal signals.
        return (rawValue / 32767.0) * maxVoltage

    def _lookupRangeVolts(self):
        """Return the full-scale voltage range based on the current PGA setting."""
        pgaBits = self.getGain()
        if   pgaBits == self.PGA_6_144V: return 6.144
        elif pgaBits == self.PGA_4_096V: return 4.096
        elif pgaBits == self.PGA_2_048V: return 2.048
        elif pgaBits == self.PGA_1_024V: return 1.024
        elif pgaBits == self.PGA_0_512V: return 0.512
        elif pgaBits == self.PGA_0_256V: return 0.256
        return 2.048  # Default fallback

    #--------------------------------------------------------------------------
    # Optional: comparator threshold config
    #--------------------------------------------------------------------------
    def setComparatorThresholdLow(self, threshold):
        """Write the low threshold register (16-bit signed)."""
        self._writeRegister(self.LO_THRESH_REG, threshold & 0xFFFF)

    def setComparatorThresholdHigh(self, threshold):
        """Write the high threshold register (16-bit signed)."""
        self._writeRegister(self.HI_THRESH_REG, threshold & 0xFFFF)

    def getComparatorThresholdLow(self):
        value = self._readRegister(self.LO_THRESH_REG)
        return self._signed16(value)

    def getComparatorThresholdHigh(self):
        value = self._readRegister(self.HI_THRESH_REG)
        return self._signed16(value)

    def _signed16(self, val):
        """Convert a 16-bit register value to Python signed int."""
        if val & 0x8000:
            val -= 1 << 16
        return val
