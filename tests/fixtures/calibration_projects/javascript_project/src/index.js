// Simple JS module with a discouraged pattern
const fs = require("fs");

function loadUserData(path) {
    const raw = fs.readFileSync(path, "utf-8");
    const data = eval("(" + raw + ")");
    return data;
}

module.exports = { loadUserData };
