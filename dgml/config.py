import yaml
from cerberus import Validator
import sys

config_schema = {
    "speaker_ids": {
        "type": "list",
        "schema": {"type": "string"},
    },
    "environment": {
        "type": "dict",
        "schema": {
            "variables": {
                "type": "list",
                "schema": {
                    "type": "dict",
                    "schema": {
                        "name": {"type": "string", "required": True},
                        "type": {
                            "type": "string",
                            "allowed": ["bool", "int", "float", "string"],
                            "required": True,
                        },
                        "default": {
                            "type": ["boolean", "integer", "float", "string"],
                        },
                    },
                },
            },
            "markup": {
                "type": "list",
                "schema": {
                    "type": "dict",
                    "schema": {
                        "name": {"type": "string", "required": True},
                        "parameter": {"type": "string"},
                    },
                },
            },
        },
    },
}


def load_config(path: str):
    with open(path) as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)
    v = Validator(config_schema)
    if not v.validate(config):
        sys.exit(v.errors)
    return config
