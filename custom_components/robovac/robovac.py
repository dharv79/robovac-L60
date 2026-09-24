from .tuyalocalapi import TuyaDevice
from .vacuums import ROBOVAC_MODELS
from .vacuums.base import RobovacCommand


class ModelNotSupportedException(Exception):
    """This model is not supported"""


class RoboVac(TuyaDevice):
    """Tuya device bound to a specific RoboVac model definition."""

    def __init__(self, model_code, *args, **kwargs):
        if model_code not in ROBOVAC_MODELS:
            raise ModelNotSupportedException(f"Model {model_code} is not supported")

        self.model_details = ROBOVAC_MODELS[model_code]
        super().__init__(self.model_details, *args, **kwargs)

    def getRoboVacFeatures(self):
        return self.model_details.robovac_features

    def getFanSpeeds(self):
        return self.model_details.commands[RobovacCommand.FAN_SPEED]["values"]

    def getSupportedCommands(self):
        return list(self.model_details.commands)

    def getCommandCodes(self):
        return {
            key: str(value["code"] if isinstance(value, dict) else value)
            for key, value in self.model_details.commands.items()
        }
