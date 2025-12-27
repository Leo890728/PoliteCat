import inspect
import unicodedata

from enum import IntEnum
from collections import Counter, ChainMap
from itertools import chain, starmap
from io import BytesIO
from pathlib import Path

import aiohttp

from colorthief import ColorThief


__all__ = (
    "fix_doc",
    "get_absolute_name_from_path",
    "get_image_dominant_color",
    "CharWidthCounter",
    "CharTypeWidth",
)


def fix_doc(*doc: str):
    """
    Clean up indentation from docstrings.
    Any whitespace that can be uniformly removed from the second line
    onwards is removed.

    Parameters:
    -----------
    *doc: list[`str`]
        A doc that needs to be formatted.
    """
    return inspect.cleandoc("\n".join(doc))


def get_absolute_name_from_path(
    path: str | Path,
    base_path: str | Path | None = None,
) -> str:
    """
    Converts absolute paths to relative positions.

    Parameters:
    -----------
    path: `str` | `Path`
        The absolute path that needs to be converted.
    base_path: `str` | `Path` | None
        The primary path of the relative path.
    """
    if not base_path:
        from bot import __config_path__

        base_path = __config_path__

    paths = [(p := Path(path).resolve()).stem]

    while not Path(base_path).samefile(p := p.parent):
        paths.append(p.stem)

    return ".".join(reversed(paths))


async def get_image_dominant_color(url: str, quality: int = 1) -> tuple[int, int, int]:
    try:
        # Open a session to fetch the image
        async with aiohttp.ClientSession() as client:
            async with client.get(url) as resp:
                # Ensure the request was successful (status code 200)
                resp.raise_for_status()  # This will raise an error for 4xx/5xx responses
                image_data = await resp.read()  # Read the content of the response

        # Process the image using ColorThief
        color_thief = ColorThief(BytesIO(image_data))
        dominant_color = color_thief.get_color(
            quality=quality)  # Extract the dominant color
        return dominant_color
    except (aiohttp.ClientResponseError, aiohttp.ClientConnectionError) as e:
        # Handle HTTP errors (e.g., bad response or connection issues)
        print(f"Error fetching image from {url}: {e}")
        return (0, 0, 0)  # Return a default color on error
    except Exception as e:
        # Catch all other exceptions (e.g., ColorThief or image processing errors)
        print(f"Unexpected error: {e}")
        return (0, 0, 0)  # Return a default color on error


class CharTypeEnum(IntEnum):
    def __new__(cls, value, *values):
        self = int.__new__(cls, value)
        self._value_ = value
        for v in values:
            self._add_value_alias_(v)
        return self


class CharTypeWidth(CharTypeEnum):
    HALF = 1, "H", "Na", "N"
    FULL = 2, "F", "A", "W"


class CharWidthCounter(Counter):
    def __init__(self, chars):
        self.char_index_map = dict()
        self.char_width_map = dict()
        self.char_chain = ChainMap(self.char_width_map, self.char_index_map)
        
        super().__init__(chars)
    
    def __getitem__(self, key):
        if isinstance(key, slice):
            counter = 0
            result_len = 0
            result = []
            for w in self.elements():
                counter += self.char_width_map[w]
                if counter in range(key.start or 0, key.stop + 1):
                    result_len += self.char_width_map[w]
                    result.append(w)
                    
            if (key.stop - (key.start or 0) + 1) - result_len:
                result.append(" ")
            return self.__class__("".join(result))
        else:
            return super().__getitem__(key)

    def update(self, string: str):
        if isinstance(string, str):
            chars_width = []
            for i, char in enumerate(string, start=self.total()):
                self.char_index_map.setdefault(char, list()).append(i)
                self.char_width_map[char] = (ctw := CharTypeWidth(unicodedata.east_asian_width(char)))
                chars_width.append(ctw)
            super().update(chars_width)
        else:
            raise ValueError("{}".format(string))
                    
    def subtract(self, string=None):
        pass

    def just(self, pos, width):
        if self.width() >= width:
            return "".join(self.elements())
        match pos:
            case "left":
                return "".join(self.elements()) + " " * (width - self.width())
            case "right":
                return " " * (width - self.width()) + "".join(self.elements())
            case "center":
                w, pw = divmod(width - self.width(), 2)
                return " " * w + "".join(self.elements()) + " " * (w + pw)
            case _:
                return "".join(self.elements())
        
    def width(self):
        return sum(starmap(lambda a, b: a * b, self.items()))
        
    def elements(self):
        elements_map = starmap(lambda char, indices: ((index, char) for index in indices), self.char_index_map.items())
        elements = list(chain.from_iterable(elements_map))
        elements.sort(key=lambda elm: elm[0])
        return list(map(lambda elm: elm[1], elements))
