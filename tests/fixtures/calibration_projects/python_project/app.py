"""Demo Python app with a minor lint issue."""

import json


def load_config(path):
    data = json.load(open(path))
    return data


def greet(name="World"):
    print(f"Hello, {name}!")


if __name__ == "__main__":
    greet()
