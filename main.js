const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

function getPythonExecutable() {
    const baseDir = app.isPackaged ? process.resourcesPath : __dirname;
    const candidates = [
        path.join(baseDir, '.venv', 'Scripts', 'python.exe'),
        path.join(baseDir, 'venv', 'Scripts', 'python.exe'),
        path.join(__dirname, '.venv', 'Scripts', 'python.exe'),
        path.join(__dirname, 'venv', 'Scripts', 'python.exe')
    ];

    const pythonExecutable = candidates.find(candidate => fs.existsSync(candidate));
    if (!pythonExecutable) {
        throw new Error(`Python executable not found. Checked: ${candidates.join(', ')}`);
    }

    return pythonExecutable;
}

function getBackendScriptPath(scriptName) {
    const baseDir = app.isPackaged ? process.resourcesPath : __dirname;
    return path.join(baseDir, 'backend', scriptName);
}

function getPythonEnvironment() {
    return {
        ...process.env,
        CBH_TRAINING_DIR: getCbhTrainingDirectory()
    };
}

function createWindow() {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        }
    });
    win.loadFile('index.html');
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});

function getCbhModelDirectory() {
    return path.join(getCbhTrainingDirectory(), 'models');
}

function getCbhTrainingDirectory() {
    if (app.isPackaged) {
        return path.join(app.getPath('userData'), 'cbh_training');
    }
    return path.join(__dirname, 'data', 'cbh_training');
}

ipcMain.handle('list-cbh-models', async () => {
    const modelDir = getCbhModelDirectory();
    if (!fs.existsSync(modelDir)) {
        return [];
    }

    return fs.readdirSync(modelDir)
        .filter(fileName => fileName.toLowerCase().endsWith('.pkl'))
        .map(fileName => {
            const modelPath = path.join(modelDir, fileName);
            const stat = fs.statSync(modelPath);
            return {
                name: fileName,
                path: modelPath,
                modifiedMs: stat.mtimeMs
            };
        })
        .sort((a, b) => b.modifiedMs - a.modifiedMs);
});

// --- NEW HANDLER: Background Pre-cache ---
ipcMain.handle('start-precache', async (event, inputPath) => {
    // We launch the process and don't wait for the result.
    // The Python script handles file locking to prevent conflicts.
    const pythonExecutable = getPythonExecutable();
    const scriptPath = getBackendScriptPath('generate_chm.py');

    console.log(`Starting background pre-cache for: ${inputPath}`);
    
    // Pass the flag --precache
    const pythonProcess = spawn(
        pythonExecutable,
        ['-u', scriptPath, inputPath, '--precache'],
        { env: getPythonEnvironment() }
    );
    pythonProcess.on('error', (error) => {
        console.error(`Pre-cache failed to start: ${error.message}`);
    });
    
    return { status: 'started' };
});

// --- HANDLER: Generate Histogram ---
ipcMain.handle('generate-histogram', async (event, inputPath) => {
    return new Promise((resolve, reject) => {
        let pythonExecutable;
        try {
            pythonExecutable = getPythonExecutable();
        } catch (error) {
            reject(error.message);
            return;
        }

        const scriptPath = getBackendScriptPath('generate_histogram.py');
        const tempDir = app.getPath('temp'); 
        const imgName = `hist_${Date.now()}.png`;
        const outputPath = path.join(tempDir, imgName);

        const scriptArgs = ['-u', scriptPath, inputPath, outputPath];
        const pythonProcess = spawn(pythonExecutable, scriptArgs, { env: getPythonEnvironment() });

        let dataString = '';
        pythonProcess.stdout.on('data', (data) => { dataString += data.toString(); });
        pythonProcess.stderr.on('data', (data) => { console.error(`Histogram Error: ${data}`); });
        pythonProcess.on('error', (error) => { reject(`Histogram failed to start: ${error.message}`); });

        pythonProcess.on('close', (code) => {
            if (code === 0) {
                try {
                    const lines = dataString.trim().split('\n');
                    const lastLine = lines[lines.length - 1];
                    const jsonResponse = JSON.parse(lastLine);
                    resolve(jsonResponse);
                } catch (e) { reject(`Failed to parse histogram response.`); }
            } else { reject(`Histogram process exited with code ${code}`); }
        });
    });
});

// --- HANDLER: Run Python (CHM / Cover) ---
ipcMain.handle('run-python', async (event, args) => {
    const { inputPath, mode, resolution, thresholds, cbhParams } = args; 
    const win = BrowserWindow.fromWebContents(event.sender);
    const dir = path.dirname(inputPath);
    const ext = path.extname(inputPath);
    const name = path.basename(inputPath, ext);

    let finalOutputPath = '';

    if (mode === 'cbh') {
        const cbhWorkflow = cbhParams && cbhParams.workflow ? cbhParams.workflow : 'train';
        const defaultSuffix = cbhWorkflow === 'predict' ? 'cbh_prediction' : 'cbh_training';
        const defaultPath = path.join(dir, `${name}_${defaultSuffix}_${resolution}m`);
        const { canceled, filePaths } = await dialog.showOpenDialog(win, {
            title: cbhWorkflow === 'predict' ? 'Choose CBH Prediction Output Folder' : 'Choose CBH Training Output Folder',
            defaultPath,
            properties: ['openDirectory', 'createDirectory']
        });

        if (canceled || filePaths.length === 0) {
            return { status: 'cancelled' };
        }

        finalOutputPath = filePaths[0];
    } else {
        let baseOutputName = '';
        if (mode === 'cover') {
            const bandCount = (thresholds && thresholds.length > 0) ? thresholds.length + 1 : 1;
            baseOutputName = `${name}_${mode}_${bandCount}bands_${resolution}m.tif`;
        } else {
            baseOutputName = `${name}_${mode}_${resolution}m.tif`;
        }

        const { canceled, filePath } = await dialog.showSaveDialog(win, {
            title: 'Save Raster Output',
            defaultPath: path.join(dir, baseOutputName),
            filters: [
                { name: 'GeoTIFF', extensions: ['tif', 'tiff'] },
                { name: 'All Files', extensions: ['*'] }
            ]
        });

        if (canceled) {
            return { status: 'cancelled' };
        }
        finalOutputPath = filePath;
    }

    return new Promise((resolve, reject) => {
        let pythonExecutable;
        try {
            pythonExecutable = getPythonExecutable();
        } catch (error) {
            reject(error.message);
            return;
        }
        
        let scriptName = '';
        if (mode === 'height') scriptName = 'generate_chm.py';
        else if (mode === 'cover') scriptName = 'generate_cover.py';
        else if (mode === 'cbh') {
            const cbhWorkflow = cbhParams && cbhParams.workflow ? cbhParams.workflow : 'train';
            scriptName = cbhWorkflow === 'predict' ? 'predict_cbh.py' : 'generate_cbh.py';
        }
        else return reject(`Unknown mode selected: ${mode}`);

        const scriptPath = getBackendScriptPath(scriptName);

        console.log(`Processing: ${inputPath}`);
        console.log(`Saving to: ${finalOutputPath}`);

        let finalJsonResult = null;
        let capturedError = '';

        if (mode === 'cbh') {
            const cbhWorkflow = cbhParams && cbhParams.workflow ? cbhParams.workflow : 'train';
            const paramsToSend = { ...(cbhParams || {}) };
            delete paramsToSend.workflow;
            if (cbhWorkflow === 'train') {
                paramsToSend.trainModel = true;
            }

            const scriptArgs = [
                '-u', scriptPath, inputPath, finalOutputPath, resolution
            ];
            if (cbhWorkflow === 'predict') {
                if (!cbhParams || !cbhParams.modelPath) {
                    return reject('Select a CBH model before running prediction.');
                }
                scriptArgs.push(cbhParams.modelPath);
            }
            scriptArgs.push(JSON.stringify(paramsToSend));
            runProcess(scriptArgs);
        } else {
            const scriptArgs = [
                '-u', scriptPath, inputPath, finalOutputPath, resolution
            ];
            const thresholdsToSend = thresholds || [];
            scriptArgs.push(JSON.stringify(thresholdsToSend));
            runProcess(scriptArgs);
        }

        function runProcess(scriptArgs) {
            const pythonProcess = spawn(pythonExecutable, scriptArgs, { env: getPythonEnvironment() });

            pythonProcess.stdout.on('data', (data) => {
            const outputStr = data.toString();
            const lines = outputStr.split('\n');
            lines.forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;
                try {
                    const json = JSON.parse(trimmed);
                    if (json.progress !== undefined) {
                        event.sender.send('progress-update', json);
                    } else if (json.status !== undefined) {
                        finalJsonResult = json;
                    }
                } catch (e) {}
            });
            });

            pythonProcess.stderr.on('data', (data) => {
                console.error(`Python Error: ${data}`);
                capturedError += data.toString();
            });

            pythonProcess.on('error', (error) => {
                reject(`Python process failed to start: ${error.message}`);
            });

            pythonProcess.on('close', (code) => {
                if (code === 0) {
                    if (finalJsonResult) {
                        if (!finalJsonResult.file) {
                            finalJsonResult.file = finalOutputPath;
                        }
                        resolve(finalJsonResult);
                    } else {
                        reject(`Process finished but returned no valid JSON result.`);
                    }
                } else {
                    reject(`Process exited with code ${code}. Stderr: ${capturedError}`);
                }
            });
        }
    });
});
