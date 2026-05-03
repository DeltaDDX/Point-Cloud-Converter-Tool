const fileInput = document.getElementById('fileInput');
const runBtn = document.getElementById('runBtn');
const statusDiv = document.getElementById('status');
const sliderDivElement = document.querySelector('.js-slider-bars');
const resamplingDivElement = document.querySelector('.js-resampling-options');
const modeSelector = document.querySelector('.js-mode-select');

const histBtn = document.getElementById('histBtn');
const histStatus = document.getElementById('histStatus');
const imageModal = document.getElementById('imageModal');
const modalImg = document.getElementById('modalImg');
const closeModal = document.getElementById('closeModal');

const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');

let currentHistogramPath = null;

function createDividedSlider(maxValue, numberOfPieces) {
    const slider = document.querySelector('.js-slider-container');

    if(!slider) return;

    // 1. Destroy existing slider if it exists to prevent duplicates
    if (slider.noUiSlider) {
        slider.noUiSlider.destroy();
    }

    // 2. Calculate initial handle positions
    // If we want 4 pieces, we need 3 handles (cuts)
    // We space them evenly to start
    let startPositions = [];
    let step = maxValue / numberOfPieces;
    for (let i = 1; i < numberOfPieces; i++) {
        startPositions.push(step * i);
    }

    // 3. Initialize noUiSlider
    noUiSlider.create(slider, {
        start: startPositions, // The array of handle positions
        connect: false,        // We don't need colored bars between handles
        step: 1,
        range: {
            'min': 0,
            'max': maxValue
        },
        format: {
            to: function (value) {
                return Math.round(value);
            },
            from: function (value) {
                return Number(value);
            }
        },
        tooltips: true,        // Shows the numbers above the handles
        pips: {                // Shows the ruler/numbers below
            mode: 'count',
            values: 8,
            density: 3,

        }
    });

    // 4. Listen for updates (optional)
    slider.noUiSlider.on('update', function (values, handle) {
        // values contains the current position of all handles
        console.log("Current handle positions:", values);
    });
}

function updateSlider(){
    const bandCountInput = document.querySelector('.js-band-count');

    if(!bandCountInput) return;
    const val = parseInt(bandCountInput.value);
    createDividedSlider(70, val);
}


fileInput.addEventListener('change', async (e) => {
    if(fileInput.files[0]) {
        // 1. Get Path
        const filePath = window.electronAPI.getFilePath(fileInput.files[0]);

        window.electronAPI.startPrecache(filePath);

        // 2. Reset UI for Histogram
        histBtn.disabled = true;
        histBtn.innerText = "Generating...";
        histStatus.innerText = "Analyzing file geometry...";
        currentHistogramPath = null;

        try {
            // 3. Trigger Background Process (Async)
            // We do NOT await this inside a blocking block if we want the UI responsive,
            // but since JS is single threaded, we trigger it and handle the promise result.
            const response = await window.electronAPI.generateHistogram(filePath);
            
            if (response.status === 'success') {
                currentHistogramPath = response.file;
                histBtn.disabled = false;
                histBtn.innerText = "View Histogram";
                histStatus.innerText = "Histogram ready";
            } else {
                histStatus.innerText = "Failed to generate histogram";
                console.error(response.message);
                histBtn.innerText = "Error";
            }
        } catch (err) {
            histStatus.innerText = "Error generating histogram";
            console.error(err);
            histBtn.innerText = "Error";
        }
    }
});

histBtn.addEventListener('click', () => {
    if (currentHistogramPath) {
        modalImg.src = currentHistogramPath;
        imageModal.style.display = "block";
    }
});

closeModal.addEventListener('click', () => {
    imageModal.style.display = "none";
});

// Close modal if user clicks outside the image
window.onclick = function(event) {
    if (event.target == imageModal) {
        imageModal.style.display = "none";
    }
}

const btnFill = document.getElementById('btnFill');
const btnText = document.getElementById('btnText');

window.electronAPI.onProgress((data) => {
    // Fill the bar
    btnFill.style.width = data.progress + '%';
    // Update text (e.g., "Scanning... 45%")
    // We switch text color to white once the bar is roughly halfway to ensure readability
    if (data.progress > 50) {
        runBtn.style.color = 'white';
    }
    btnText.innerText = `${data.text} (${data.progress}%)`;
});

modeSelector.addEventListener('change', (e) => {
    const selectedMode = modeSelector.value;
    
    if (selectedMode === 'cover') {
        resamplingDivElement.innerHTML = ``;
        // 1. Inject the HTML (WITH TOOLTIP ADDED)
        sliderDivElement.innerHTML = `
            <label class="has-tooltip" data-tooltip="Number of layers to split the canopy cover raster into">4. Raster Bands (Divided by sliders)</label>
            <input type="number" id="bandCount" class="js-band-count" value="4" min="1" max="10">
            <div class="slider-container js-slider-container" style=" margin-top: 55px; margin-bottom: 60px; margin-left: 5px; margin-right: 5px"></div>
        `;

        // 2. Add event listener to the NEW input element
        document.querySelector('.js-band-count').addEventListener('change', updateSlider);

        // 3. ACTUALLY DRAW THE SLIDER NOW
        updateSlider(); 
    } else if (selectedMode === 'cbh') {
        sliderDivElement.innerHTML = '';
        resamplingDivElement.innerHTML = `
            <label class="has-tooltip" data-tooltip="Parameters for proxy labels and feature rasters">4. CBH Extraction Parameters</label>
            <div class="subgrid">
                <div>
                    <label class="has-tooltip" data-tooltip="Minimum height considered canopy base, in meters">Minimum Canopy Height</label>
                    <input type="number" id="cbhMinCanopyHeight" value="2" step="0.1" min="0">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Vertical profile bin size, in meters">Height Bin Size</label>
                    <input type="number" id="cbhHeightBinSize" value="0.5" step="0.1" min="0.1">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Maximum normalized point height to profile, in meters">Maximum Profile Height</label>
                    <input type="number" id="cbhMaxProfileHeight" value="60" step="1" min="1">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Minimum returns in a cell before it can be used">Minimum Cell Returns</label>
                    <input type="number" id="cbhMinColumnPoints" value="5" step="1" min="1">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Minimum returns needed for a vertical bin to count as occupied">Minimum Bin Returns</label>
                    <input type="number" id="cbhMinBinPoints" value="2" step="1" min="1">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Allowed empty bins inside a sustained canopy segment">Gap Tolerance Bins</label>
                    <input type="number" id="cbhGapToleranceBins" value="1" step="1" min="0">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Occupied bins needed after first canopy hit">Minimum Canopy Depth Bins</label>
                    <input type="number" id="cbhMinCanopyDepthBins" value="2" step="1" min="1">
                </div>
                <div>
                    <label class="has-tooltip" data-tooltip="Cells below this cover ratio are constrained to zero CBH">Cover Ratio Threshold</label>
                    <input type="number" id="cbhCoverThreshold" value="0.1" step="0.01" min="0" max="1">
                </div>
            </div>
            <div style="margin-top: 12px;">
                <label class="has-tooltip" data-tooltip="Comma-separated normalized-height percentile features">Height Percentiles</label>
                <input type="text" id="cbhHeightPercentiles" value="10,25,50,75,90,95">
            </div>
            <div style="margin-top: 12px;">
                <label class="has-tooltip" data-tooltip="Comma-separated height thresholds for cover-ratio features">Cover Feature Thresholds (m)</label>
                <input type="text" id="cbhCoverThresholds" value="0.5,1,2,5">
            </div>
            <div class="field-note">Outputs are written to a folder: proxy labels, feature rasters, diagnostics, and a CSV training table.</div>
        `;
    } else {
        // Clear it if they switch back to Height
        sliderDivElement.innerHTML = ''; 

        // (WITH TOOLTIP ADDED)
        resamplingDivElement.innerHTML = `
        <label class="has-tooltip" data-tooltip="Percentile used as the tree top height (e.g., 95%)">4. Relative Height Percentile (RH %)</label>
            <input type="number" id="resampleInput" class="js-resample-select" min="1" max="100" value="95">
        `;
    }
});

function parseNumberInput(id, label, options = {}) {
    const input = document.getElementById(id);
    const value = Number(input.value);
    if (!Number.isFinite(value)) {
        throw new Error(`${label} must be a number.`);
    }
    if (options.integer && !Number.isInteger(value)) {
        throw new Error(`${label} must be a whole number.`);
    }
    if (options.min !== undefined && value < options.min) {
        throw new Error(`${label} must be at least ${options.min}.`);
    }
    if (options.max !== undefined && value > options.max) {
        throw new Error(`${label} must be no more than ${options.max}.`);
    }
    return value;
}

function parseNumberListInput(id, label, options = {}) {
    const input = document.getElementById(id);
    const values = input.value
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)
        .map(Number);

    if (values.length === 0 || values.some((value) => !Number.isFinite(value))) {
        throw new Error(`${label} must be a comma-separated list of numbers.`);
    }
    if (options.min !== undefined && values.some((value) => value < options.min)) {
        throw new Error(`${label} cannot include values below ${options.min}.`);
    }
    if (options.max !== undefined && values.some((value) => value > options.max)) {
        throw new Error(`${label} cannot include values above ${options.max}.`);
    }
    return values;
}

function getCbhParams() {
    return {
        minCanopyHeight: parseNumberInput('cbhMinCanopyHeight', 'Minimum Canopy Height', { min: 0 }),
        heightBinSize: parseNumberInput('cbhHeightBinSize', 'Height Bin Size', { min: 0.1 }),
        maxProfileHeight: parseNumberInput('cbhMaxProfileHeight', 'Maximum Profile Height', { min: 1 }),
        minColumnPoints: parseNumberInput('cbhMinColumnPoints', 'Minimum Cell Returns', { min: 1, integer: true }),
        minBinPoints: parseNumberInput('cbhMinBinPoints', 'Minimum Bin Returns', { min: 1, integer: true }),
        gapToleranceBins: parseNumberInput('cbhGapToleranceBins', 'Gap Tolerance Bins', { min: 0, integer: true }),
        minCanopyDepthBins: parseNumberInput('cbhMinCanopyDepthBins', 'Minimum Canopy Depth Bins', { min: 1, integer: true }),
        coverThreshold: parseNumberInput('cbhCoverThreshold', 'Cover Ratio Threshold', { min: 0, max: 1 }),
        heightPercentiles: parseNumberListInput('cbhHeightPercentiles', 'Height Percentiles', { min: 0, max: 100 }),
        coverThresholds: parseNumberListInput('cbhCoverThresholds', 'Cover Feature Thresholds', { min: 0 })
    };
}


// renderer.js

runBtn.addEventListener('click', async () => {
    if (fileInput.files.length === 0) {
        alert("Please select a file first.");
        return;
    }

    const filePath = window.electronAPI.getFilePath(fileInput.files[0]);
    const mode = document.getElementById('modeInput').value;
    const resolution = document.getElementById('resInput').value;
    
    // Get thresholds
    let thresholds = [];
    let cbhParams = null;
    const slider = document.querySelector('.js-slider-container');
    if (mode === 'cover' && slider && slider.noUiSlider) {
        const rawValues = slider.noUiSlider.get();
        const valuesArray = Array.isArray(rawValues) ? rawValues : [rawValues];
        thresholds = valuesArray.map(Number);
    } else if (mode === 'height') {

        const resampleInput = document.getElementById('resampleInput');
        const val = Number(resampleInput.value);
        if (!Number.isInteger(val)) {
            alert("Please enter a whole number (no decimals).");
            runBtn.disabled = false;
            return;
        }
        if (val < 1 || val > 100) {
            alert("Relative Height (RH %) must be between 1 and 100.");
            runBtn.disabled = false;
            return;
        }
        
        thresholds = val;
    } else if (mode === 'cbh') {
        try {
            cbhParams = getCbhParams();
        } catch (err) {
            alert(err.message);
            runBtn.disabled = false;
            return;
        }
    }

    // --- UI SETUP FOR LOADING ---
    statusDiv.style.display = 'block';
    statusDiv.className = 'info';
    statusDiv.innerText = "Processing... (Large files may take a while)"; // Updated text
    
    runBtn.disabled = true;
    runBtn.classList.add('loading'); 
    btnFill.style.width = '0%';
    btnText.innerText = "Initializing...";
    
    try {
        const response = await window.electronAPI.runPython({
            inputPath: filePath,
            mode: mode,
            resolution: resolution,
            thresholds: thresholds,
            cbhParams: cbhParams
        });

        if (response.status === 'success') {
            statusDiv.style.display = 'block';
            statusDiv.className = 'success';
            // This now uses the path the user selected
            statusDiv.innerText = `Success! Saved to:\n${response.file}`;
        } 
        else if (response.status === 'cancelled') {
            // User hit Cancel in the Save Dialog
            statusDiv.style.display = 'none'; // Hide the "Processing" message
        } 
        else {
            statusDiv.style.display = 'block';
            statusDiv.className = 'error';
            statusDiv.innerText = `Error: ${response.message}`;
        }
    } catch (err) {
        statusDiv.style.display = 'block';
        statusDiv.className = 'error';
        statusDiv.innerText = `System Error: ${err}`;
    } finally {
        // --- RESET BUTTON UI ---
        runBtn.disabled = false;
        runBtn.classList.remove('loading'); 
        btnFill.style.width = '0%';       
        btnText.innerText = "Generate Raster"; 
        runBtn.style.color = 'white';     
    }
});
