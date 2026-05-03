const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    runPython: (args) => ipcRenderer.invoke('run-python', args),
    // This helper function safely extracts the path
    getFilePath: (file) => webUtils.getPathForFile(file),

    generateHistogram: (path) => ipcRenderer.invoke('generate-histogram', path),
    listCbhModels: () => ipcRenderer.invoke('list-cbh-models'),
    
    onProgress: (callback) => ipcRenderer.on('progress-update', (event, value) => callback(value)),

    startPrecache: (path) => ipcRenderer.invoke('start-precache', path)
});
