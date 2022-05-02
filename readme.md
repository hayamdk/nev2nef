# Nev2Nef
Nev2Nef is a extractor of Z9 NEV(Nikon RAW, N-RAW) video to indivisual NEF frames.

# Overview
N-RAW video file and high efficiency raw of Z9 has same structure data which is assume to be TicoRAW.
So extract TicoRAW data from N-RAW video and insert to already exists high efficiency raw file, then it become an indivisual frames of N-RAW video.
An ticoRAW data starts with magic number: 0xff10ff50, followed by "CONTACT_INTOPIX" string.

# Install
- Python3
Windows: From Microsoft Store or download installer from https://www.python.org/downloads/.

- PySide2
Execute folloing command: `pip install PySide2`

# Convert to lossless DNG
High efficiency raw (ticoRAW) files are decodable by limited applications. So it is useful to convert regular lossless DNG files.
Adobe DNG Converter can convert high efficiency raw files to regular lossless DNG files.
https://helpx.adobe.com/jp/photoshop/using/adobe-dng-converter.html

# Limitations
- All metadata (such as shutter-speed, f-number, or ISO sensitivity) of generated NEF file will be derived from template NEF file.

# Known issue
- Currently, 5.4K raw is not supported by Adobe DNG Converter.