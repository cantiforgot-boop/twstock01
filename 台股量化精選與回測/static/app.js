document.addEventListener('DOMContentLoaded', () => {
    // Detect environment
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    // Global state
    let pollingInterval = null;
    let returnChart = null;
    let winRateChart = null;

    // Elements
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const btnRunLong = document.getElementById('btn-run-long');
    const btnRunShort = document.getElementById('btn-run-short');
    const consoleLog = document.getElementById('console-log');
    const consoleStatusText = document.getElementById('console-status-text');
    const historyFilesBody = document.getElementById('history-files-body');
    const detailTitle = document.getElementById('detail-title');
    const detailActionsPanel = document.getElementById('detail-actions-panel');
    const detailDateBadge = document.getElementById('detail-date-badge');
    const detailTypeBadge = document.getElementById('detail-type-badge');
    const detailTableHeaders = document.getElementById('detail-table-headers');
    const detailDataBody = document.getElementById('detail-data-body');

    // UI adjustments for GitHub Pages (Non-local)
    if (!isLocal) {
        if (btnRunLong) btnRunLong.style.display = 'none';
        if (btnRunShort) btnRunShort.style.display = 'none';
        consoleLog.textContent = "☁️ 雲端自動化排程已啟用\n------------------------------\n排程設定：\n每個台股交易日 (週一至週五)\n- 18:00 自動執行多方選股與回測\n- 18:05 自動執行空方選股與回測\n\n最新選股資料將會自動同步至本頁面。";
        consoleStatusText.innerHTML = `<span class="dot running" style="background-color: #00f2fe; box-shadow: 0 0 8px #00f2fe;"></span> 24H 雲端排程監控中`;
    }

    // TAB SWITCHING
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(tabId).classList.add('active');

            if (tabId === 'history') {
                loadHistoryFiles();
            } else if (tabId === 'stats') {
                loadStats();
            }
        });
    });

    // POLLING STATUS (Local only)
    function startPollingStatus() {
        if (!isLocal) return;
        if (pollingInterval) clearInterval(pollingInterval);
        
        btnRunLong.disabled = true;
        btnRunShort.disabled = true;

        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                updateConsole(data);
                
                if (!data.is_running) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                    btnRunLong.disabled = false;
                    btnRunShort.disabled = false;
                }
            } catch (err) {
                console.error("Error polling status:", err);
            }
        }, 1000);
    }

    function updateConsole(data) {
        if (data.is_running) {
            consoleStatusText.innerHTML = `<span class="dot running"></span> 正在執行 ${data.strategy === 'long' ? '多方' : '空方'} 選股中...`;
        } else {
            consoleStatusText.innerHTML = `<span class="dot idle"></span> 系統閒置中`;
        }

        if (data.logs && data.logs.length > 0) {
            consoleLog.textContent = data.logs.join('\n');
            consoleLog.scrollTop = consoleLog.scrollHeight;
        } else {
            consoleLog.textContent = "等待執行指令...";
        }
    }

    // TRIGGER RUNS (Local only)
    async function triggerRun(strategy) {
        if (!isLocal) return;
        try {
            consoleLog.textContent = "發送請求中...";
            const response = await fetch(`/api/run/${strategy}`, { method: 'POST' });
            const data = await response.json();
            
            if (response.ok) {
                startPollingStatus();
            } else {
                consoleLog.textContent = `[錯誤] ${data.message}`;
            }
        } catch (err) {
            consoleLog.textContent = `[連線錯誤] ${err.message}`;
        }
    }

    if (isLocal) {
        btnRunLong.addEventListener('click', () => triggerRun('long'));
        btnRunShort.addEventListener('click', () => triggerRun('short'));
    }

    // LOAD HISTORY FILES LIST
    async function loadHistoryFiles() {
        try {
            historyFilesBody.innerHTML = `<tr><td colspan="6" class="text-center">讀取歷史目錄中...</td></tr>`;
            
            // Adaptive route: Flask API locally, static index JSON on GitHub Pages
            const url = isLocal ? '/api/history' : 'data/history_index.json';
            const response = await fetch(url);
            const data = await response.json();
            
            if (data.length === 0) {
                historyFilesBody.innerHTML = `<tr><td colspan="6" class="text-center">目前無歷史報表數據</td></tr>`;
                return;
            }
            
            historyFilesBody.innerHTML = '';
            data.forEach(item => {
                const tr = document.createElement('tr');
                tr.dataset.filename = item.filename;
                tr.dataset.date = item.date;
                tr.dataset.strategy = item.strategy;
                tr.dataset.strategyType = item.strategy_type;

                const isLong = item.strategy_type === 'long';
                const classT5 = getReturnClass(item.t5, isLong);
                const classT10 = getReturnClass(item.t10, isLong);
                const classT20 = getReturnClass(item.t20, isLong);

                tr.innerHTML = `
                    <td>${item.date}</td>
                    <td><span class="strategy-badge ${item.strategy_type}">${item.strategy}</span></td>
                    <td>${item.count} 檔</td>
                    <td class="${classT5}">${item.t5}</td>
                    <td class="${classT10}">${item.t10}</td>
                    <td class="${classT20}">${item.t20}</td>
                `;

                tr.addEventListener('click', () => {
                    document.querySelectorAll('#history-files-body tr').forEach(r => r.classList.remove('active'));
                    tr.classList.add('active');
                    loadReportDetail(item.filename, item.date, item.strategy, item.strategy_type);
                });

                historyFilesBody.appendChild(tr);
            });
        } catch (err) {
            historyFilesBody.innerHTML = `<tr><td colspan="6" class="text-center text-down">載入失敗: ${err.message}</td></tr>`;
        }
    }

    function getReturnClass(valStr, isLong) {
        if (!valStr || valStr === 'N/A') return 'text-neutral';
        const val = parseFloat(valStr);
        if (isNaN(val)) return 'text-neutral';
        if (val === 0) return 'text-neutral';
        
        if (isLong) {
            return val > 0 ? 'text-up' : 'text-down';
        } else {
            return val < 0 ? 'text-up' : 'text-down'; // negative is profitable for shorting
        }
    }

    // JS CSV Parser for Serverless GitHub Pages mode
    function parseCSV(text) {
        const lines = text.split('\n').map(line => line.trim()).filter(line => line.length > 0);
        if (lines.length === 0) return [];
        
        const headers = lines[0].split(',');
        const records = [];
        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',');
            if (values.length === headers.length) {
                const obj = {};
                headers.forEach((h, idx) => {
                    obj[h] = values[idx];
                });
                records.push(obj);
            }
        }
        return records;
    }

    // LOAD REPORT DETAIL
    async function loadReportDetail(filename, date, strategy, strategyType) {
        try {
            detailDataBody.innerHTML = `<tr><td colspan="15" class="text-center">讀取報表詳細內容中...</td></tr>`;
            
            let data = [];
            if (isLocal) {
                const response = await fetch(`/api/report/${filename}`);
                data = await response.json();
                if (data.status === 'error') {
                    detailDataBody.innerHTML = `<tr><td colspan="15" class="text-center text-down">讀取錯誤: ${data.message}</td></tr>`;
                    return;
                }
            } else {
                // Static Pages mode: fetch CSV file directly and parse
                const response = await fetch(`data/${filename}`);
                if (!response.ok) {
                    detailDataBody.innerHTML = `<tr><td colspan="15" class="text-center text-down">無法加載 CSV 檔案</td></tr>`;
                    return;
                }
                const csvText = await response.text();
                data = parseCSV(csvText);
            }

            // Update Header badges
            detailTitle.innerHTML = `<i class="fa-solid fa-list-check"></i> ${strategy}選股報表詳情`;
            detailDateBadge.textContent = date;
            detailTypeBadge.textContent = strategy;
            detailTypeBadge.className = `type-badge ${strategyType}`;
            detailActionsPanel.style.display = 'flex';

            if (data.length === 0) {
                detailDataBody.innerHTML = `<tr><td colspan="15" class="text-center">該日無選出標的數據</td></tr>`;
                return;
            }

            // Dynamic Column Discovery
            const keys = Object.keys(data[0]);
            const coreKeys = ['股票代號', '股票名稱', '選出時收盤價', '選出日期', '5日均量', 'MACD狀態', '風險提示'];
            const trackingKeys = keys.filter(k => k.startsWith('T+') && !k.includes('日期'));
            const headerKeys = [...coreKeys.filter(k => keys.includes(k)), ...trackingKeys];
            
            // Build Table Headers HTML
            detailTableHeaders.innerHTML = headerKeys.map(k => `<th>${k}</th>`).join('');

            // Build Rows HTML
            detailDataBody.innerHTML = '';
            data.forEach(row => {
                const tr = document.createElement('tr');
                
                tr.innerHTML = headerKeys.map(k => {
                    const val = row[k];
                    let displayVal = val === null || val === undefined ? 'N/A' : val;
                    let cellClass = '';

                    if (k === '風險提示') {
                        const isHot = val === '過熱';
                        cellClass = `class="risk-tag ${isHot ? 'hot' : 'normal'}"`;
                        displayVal = `<span ${cellClass}>${val}</span>`;
                        return `<td>${displayVal}</td>`;
                    }
                    
                    if (k.includes('漲跌幅') || k.includes('跌幅')) {
                        const valNum = parseFloat(val);
                        if (!isNaN(valNum)) {
                            const isLong = strategyType === 'long';
                            const formattedVal = valNum >= 0 ? `+${valNum.toFixed(2)}%` : `${valNum.toFixed(2)}%`;
                            const signClass = getReturnClass(formattedVal, isLong);
                            return `<td class="${signClass}">${formattedVal}</td>`;
                        }
                    }

                    if (k.includes('最新收盤價') && val !== null) {
                        displayVal = parseFloat(val).toFixed(2);
                    }
                    if (k === '選出時收盤價' && val !== null) {
                        displayVal = parseFloat(val).toFixed(2);
                    }

                    return `<td class="${cellClass}">${displayVal}</td>`;
                }).join('');
                
                detailDataBody.appendChild(tr);
            });
        } catch (err) {
            detailDataBody.innerHTML = `<tr><td colspan="15" class="text-center text-down">載入詳情失敗: ${err.message}</td></tr>`;
        }
    }

    // LOAD STRATEGY STATS & CHARTS
    async function loadStats() {
        try {
            const url = isLocal ? '/api/stats' : 'data/strategy_stats.json';
            const response = await fetch(url);
            const data = await response.json();

            // Long Stats Card
            document.getElementById('stats-long-return').textContent = `${data.long.t5_avg >= 0 ? '+' : ''}${data.long.t5_avg}%`;
            document.getElementById('stats-long-return').className = data.long.t5_avg >= 0 ? 'text-up' : 'text-down';
            document.getElementById('stats-long-runs').textContent = data.long.runs;
            document.getElementById('stats-long-stocks').textContent = data.long.stocks;
            document.getElementById('stats-long-win').textContent = `${data.long.win_rate}%`;

            // Short Stats Card
            document.getElementById('stats-short-return').textContent = `${data.short.t5_avg >= 0 ? '+' : ''}${data.short.t5_avg}%`;
            document.getElementById('stats-short-return').className = data.short.t5_avg <= 0 ? 'text-up' : 'text-down';
            document.getElementById('stats-short-runs').textContent = data.short.runs;
            document.getElementById('stats-short-stocks').textContent = data.short.stocks;
            document.getElementById('stats-short-win').textContent = `${data.short.win_rate}%`;

            // Render Charts
            renderCharts(data);
        } catch (err) {
            console.error("Error loading stats:", err);
        }
    }

    function renderCharts(data) {
        const ctxReturn = document.getElementById('return-chart').getContext('2d');
        const ctxWin = document.getElementById('winrate-chart').getContext('2d');

        if (returnChart) returnChart.destroy();
        if (winRateChart) winRateChart.destroy();

        returnChart = new Chart(ctxReturn, {
            type: 'bar',
            data: {
                labels: ['多方策略 (平均漲幅)', '空方策略 (平均跌幅)'],
                datasets: [{
                    label: 'T+5 績效 (%)',
                    data: [data.long.t5_avg, -data.short.t5_avg],
                    backgroundColor: [
                        'rgba(0, 242, 254, 0.65)',
                        'rgba(245, 78, 162, 0.65)'
                    ],
                    borderColor: [
                        '#00f2fe',
                        '#f54ea2'
                    ],
                    borderWidth: 1.5,
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ` T+5 表現: ${context.parsed.y > 0 ? '+' : ''}${context.parsed.y.toFixed(2)}%`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#8c82ab' }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#8c82ab' }
                    }
                }
            }
        });

        winRateChart = new Chart(ctxWin, {
            type: 'doughnut',
            data: {
                labels: ['多方勝率', '多方敗率', '空方做空成功率', '空方做空失敗率'],
                datasets: [{
                    data: [
                        data.long.win_rate, 
                        100 - data.long.win_rate, 
                        data.short.win_rate, 
                        100 - data.short.win_rate
                    ],
                    backgroundColor: [
                        'rgba(0, 242, 254, 0.7)',
                        'rgba(255, 255, 255, 0.08)',
                        'rgba(245, 78, 162, 0.7)',
                        'rgba(255, 255, 255, 0.04)'
                    ],
                    borderColor: [
                        '#00f2fe',
                        'rgba(255, 255, 255, 0.1)',
                        '#f54ea2',
                        'rgba(255, 255, 255, 0.05)'
                    ],
                    borderWidth: 1.5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#8c82ab', padding: 15 }
                    }
                },
                cutout: '65%'
            }
        });
    }

    // Check status on load (Local only)
    async function checkStatusOnLoad() {
        if (!isLocal) return;
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            updateConsole(data);
            
            if (data.is_running) {
                startPollingStatus();
            }
        } catch (err) {
            console.error("Error reading initial status:", err);
        }
    }

    checkStatusOnLoad();
});
