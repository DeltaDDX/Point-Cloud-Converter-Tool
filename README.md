# Point-Cloud-Converter-Tool

Desktop tool for converting LAS/LAZ LiDAR point clouds into raster outputs.

The app uses Electron for the user interface and Python for point-cloud and GeoTIFF processing.

## Prerequisites

- Node.js and npm
- Python 3
- Windows PowerShell

## Setup

Install the Electron dependencies:

```powershell
npm install
```

Create a Python virtual environment in the project root. The Electron app expects Python at `venv\Scripts\python.exe`.

```powershell
python -m venv venv
```

Activate the virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

## Run the App

Start the Electron desktop app:

```powershell
npm start
```

## Basic Use

1. Select a `.las` or `.laz` point-cloud file.
2. Choose an output mode:
   - `Canopy Height Model (CHM)`
   - `Canopy Cover %`
3. Set the output resolution in meters.
4. For CHM, set the relative height percentile.
5. For cover mode, set the number of bands and adjust the height sliders.
6. Click `Generate Raster`.
7. Choose where to save the GeoTIFF output.

The app also generates a height histogram after a file is selected. Use `View Histogram` once it is ready.

## Outputs

- CHM mode writes a single-band GeoTIFF.
- Cover mode writes a multi-band GeoTIFF, with bands based on the configured height thresholds.
- Temporary histogram images are written to the system temp directory.
- Internal cached CHM files may be created next to the input point-cloud file.

## Backend Scripts

The main Electron flow calls these Python scripts:

- `backend/generate_chm.py` for canopy height models
- `backend/generate_cover.py` for canopy cover rasters
- `backend/generate_histogram.py` for histogram images

There is also a standalone helper:

```powershell
python backend\declassify.py input.laz output.laz
```

This converts ground-classified points from class `2` to class `1`.

## Notes

- Large point-cloud files can take a long time to process.
- The app reads point clouds in chunks to reduce memory pressure.
- If PowerShell blocks virtual environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
