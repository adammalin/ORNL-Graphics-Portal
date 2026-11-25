// Only selected-job attachment paths are accepted; never fetch arbitrary URLs.
export function pdfSourcePath(path){return typeof path==='string'&&/^\/api\/projects\/[A-Za-z0-9_-]+\/attachments\/[A-Za-z0-9_-]+$/.test(path)?path:null;}
