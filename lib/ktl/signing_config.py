import json
import os
from urllib.parse import urlsplit
from urllib.request import urlopen

import yaml


class SigningConfigStreamLevel:
    def __init__(self, stream, level, variant, reference):
        self.stream = stream
        self.level = int(level)
        self.variant = variant

        self.reference = reference

    @property
    def archive_reference(self):
        if self.reference is None:
            return None
        return "ppa:canonical-signing/ubuntu/" + self.reference


class SigningConfig:
    def __init__(self, url=None, data=None, data_location=None, use_local=os.getenv("USE_LOCAL_SIGNING_CONFIG", False)):
        if data_location is None:
            if use_local:
                try:
                    import ckt_info

                    path = ckt_info.abspath("info/signing-config.yaml")
                    data_location = os.path.dirname(path)
                except ImportError:
                    data_location = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "kernel-versions"))

            else:
                data_location = "https://kernel.ubuntu.com/info"

        self.data_location = data_location

        if data is None:
            if url is None:
                url = self.data_location + "/signing-config.yaml"
            url = urlsplit(url, scheme="file").geturl()
            response = urlopen(url)
            data = response.read()
            if isinstance(data, bytes):
                data = data.decode("utf-8")

        if isinstance(data, dict):
            self._data = data

        elif data.startswith("{"):
            self._data = json.loads(data)

        else:
            self._data = yaml.safe_load(data)

        # Instantiate any simple mappings as direct mappings.
        if "streams" in self._data:
            for stream, stream_data in self._data["streams"].items():
                for level, level_data in list(stream_data.items()):
                    if isinstance(level_data, str):
                        stream_data[level] = {stream: level_data}

        self._streams = self._data.get("streams", {})

    def lookup_stream(self, stream_level):
        if "/" not in stream_level:
            raise ValueError("Invalid stream/level format")
        stream, level = stream_level.split("/", 1)
        if "+" in level:
            level, variant = level.split("+")

        elif ":" in level:
            level, variant = level.split(":")

        elif "/" in level:
            variant, level = level.split("/")

        else:
            variant = stream

        return SigningConfigStreamLevel(
            stream, level, variant, self._streams.get(stream, {}).get(int(level), {}).get(variant)
        )
