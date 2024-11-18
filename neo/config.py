#!/bin/env python3

import os
import yaml

class NeoConfig(dict):
    def __init__(self, *args, **kwargs):
        cranky_config_path = os.path.expanduser(os.environ['NEO_CONFIG_FILE'])
        with open(cranky_config_path, 'r') as f:
            data = yaml.safe_load(f.read())
        super().__init__(data, *args, **kwargs)


if __name__ == '__main__':
    cfg = NeoConfig()
    print(yaml.dump(cfg, default_flow_style=False, indent=4, explicit_start=True))
