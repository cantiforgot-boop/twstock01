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
    const btnRunMargin = document.getElementById('btn-run-margin');
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
        if (btnRunMargin) btnRunMargin.style.display = 'none';
        consoleLog.textContent = "☁️ 雲端自動化排程已啟用\n------------------------------\n排程設定：\n每個台股交易日 (週一至週五)\n- 18:00 自動執行多方選股與回測\n- 18:05 自動執行空方選股與回測\n- 21:45 自動執行資券籌碼多空分析\n\n最新選股資料將會自動同步至本頁面。";
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
            } else if (tabId === 'institutional') {
                loadInstitutionalData();
            } else if (tabId === 'margin-diag') {
                loadLatestMarginDiag();
            } else if (tabId === 'market-compass') {
                loadMarketCompass();
            } else if (tabId === 'chip-horse') {
                loadChipHorse();
            } else if (tabId === 'alert-monitor') {
                loadAlertConfigs();
            }
        });
    });

    // POLLING STATUS (Local only)
    function startPollingStatus() {
        if (!isLocal) return;
        if (pollingInterval) clearInterval(pollingInterval);
        
        btnRunLong.disabled = true;
        btnRunShort.disabled = true;
        if (btnRunMargin) btnRunMargin.disabled = true;

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
                    if (btnRunMargin) btnRunMargin.disabled = false;
                }
            } catch (err) {
                console.error("Error polling status:", err);
            }
        }, 1000);
    }

    function updateConsole(data) {
        if (data.is_running) {
            let strategyName = data.strategy === 'long' ? '多方' : (data.strategy === 'short' ? '空方' : '籌碼');
            consoleStatusText.innerHTML = `<span class="dot running"></span> 正在執行 ${strategyName} 選股中...`;
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
            const volInput = document.getElementById(`param-${strategy}-vol`);
            const minVolume = volInput ? volInput.value : '';
            const url = minVolume ? `/api/run/${strategy}?min_volume=${minVolume}` : `/api/run/${strategy}`;
            
            const response = await fetch(url, { method: 'POST' });
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
        if (btnRunMargin) btnRunMargin.addEventListener('click', () => triggerRun('margin'));
    }

    // LOAD HISTORY FILES LIST
    async function loadHistoryFiles() {
        try {
            historyFilesBody.innerHTML = `<tr><td colspan="6" class="text-center">讀取歷史目錄中...</td></tr>`;
            
            // Adaptive route: Flask API locally, static index JSON on GitHub Pages
            const url = isLocal ? '/api/history' : '../data/history_index.json';
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
                const response = await fetch(`../data/${filename}`);
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
            const coreKeys = ['股票代號', '股票名稱', '選出時收盤價', '收盤價', '今日收盤價', '選出日期', '5日均量', '5日均量(張)', 'MACD狀態', '風險提示', '籌碼診斷'];
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
            const url = isLocal ? '/api/stats' : '../data/strategy_stats.json';
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
 
            // Margin Stats Card
            if (document.getElementById('stats-margin-return')) {
                document.getElementById('stats-margin-return').textContent = `${data.margin.t5_avg >= 0 ? '+' : ''}${data.margin.t5_avg}%`;
                document.getElementById('stats-margin-return').className = data.margin.t5_avg >= 0 ? 'text-up' : 'text-down';
                document.getElementById('stats-margin-runs').textContent = data.margin.runs;
                document.getElementById('stats-margin-stocks').textContent = data.margin.stocks;
                document.getElementById('stats-margin-win').textContent = `${data.margin.win_rate}%`;
            }

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
                labels: ['多方策略 (平均漲幅)', '空方策略 (平均跌幅)', '籌碼策略 (平均漲幅)'],
                datasets: [{
                    label: 'T+5 績效 (%)',
                    data: [data.long.t5_avg, -data.short.t5_avg, data.margin ? data.margin.t5_avg : 0],
                    backgroundColor: [
                        'rgba(0, 242, 254, 0.65)',
                        'rgba(245, 78, 162, 0.65)',
                        'rgba(243, 156, 18, 0.65)'
                    ],
                    borderColor: [
                        '#00f2fe',
                        '#f54ea2',
                        '#f39c12'
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
                labels: ['多方勝率', '多方敗率', '空方做空成功率', '空方做空失敗率', '籌碼勝率', '籌碼敗率'],
                datasets: [{
                    data: [
                        data.long.win_rate, 
                        100 - data.long.win_rate, 
                        data.short.win_rate, 
                        100 - data.short.win_rate,
                        data.margin ? data.margin.win_rate : 0,
                        data.margin ? (100 - data.margin.win_rate) : 100
                    ],
                    backgroundColor: [
                        'rgba(0, 242, 254, 0.7)',
                        'rgba(255, 255, 255, 0.08)',
                        'rgba(245, 78, 162, 0.7)',
                        'rgba(255, 255, 255, 0.04)',
                        'rgba(243, 156, 18, 0.7)',
                        'rgba(255, 255, 255, 0.02)'
                    ],
                    borderColor: [
                        '#00f2fe',
                        'rgba(255, 255, 255, 0.1)',
                        '#f54ea2',
                        'rgba(255, 255, 255, 0.05)',
                        '#f39c12',
                        'rgba(255, 255, 255, 0.02)'
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

    // =========================================================================
    // INSTITUTIONAL TRADING & VOLUME TRACKER
    // =========================================================================

    // Top-Level Sub-Tabs Switcher (Institutional Streak vs Volume Analysis)
    const mainSubTabBtns = document.querySelectorAll('#institutional .main-sub-tabs .sub-tab-btn');
    const mainSubTabPanes = document.querySelectorAll('#institutional .main-sub-tab-pane');
    
    mainSubTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const subTabId = btn.dataset.subTab;
            mainSubTabBtns.forEach(b => b.classList.remove('active'));
            mainSubTabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(subTabId).classList.add('active');
        });
    });

    // Secondary Sub-tabs (Streak Tracker categories: Both, Foreign, SITC)
    const streakSubTabBtns = document.querySelectorAll('#institutional .sub-tabs:not(.main-sub-tabs) .sub-tab-btn');
    const streakSubTabPanes = document.querySelectorAll('#institutional .sub-tab-pane');
    
    streakSubTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const subTabId = btn.dataset.subTab;
            streakSubTabBtns.forEach(b => b.classList.remove('active'));
            streakSubTabPanes.forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            document.getElementById(subTabId).classList.add('active');
        });
    });

    // Controls and Buttons
    const btnRefreshInst = document.getElementById('btn-refresh-inst');
    const selectConsecutiveDays = document.getElementById('consecutive-days-select');
    const instDatesInfo = document.getElementById('inst-dates-info');
    
    if (btnRefreshInst) {
        btnRefreshInst.addEventListener('click', loadInstitutionalData);
    }
    if (selectConsecutiveDays) {
        selectConsecutiveDays.addEventListener('change', loadInstitutionalData);
    }

    async function loadInstitutionalData() {
        const days = selectConsecutiveDays.value;
        instDatesInfo.textContent = "🔍 正在載入法人籌碼數據，請稍後...";
        
        // Show loading state in tables
        const tables = [
            'table-both-buy-body', 'table-both-sell-body',
            'table-foreign-buy-body', 'table-foreign-sell-body',
            'table-sitc-buy-body', 'table-sitc-sell-body'
        ];
        tables.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<tr><td colspan="${id.includes('both') ? 6 : 5}" class="text-center">載入中...</td></tr>`;
        });

        try {
            const resp = await fetch(isLocal ? `/api/institutional?days=${days}` : `../data/institutional_${days}.json`);
            const json = await resp.json();
            
            if (json.status === 'success') {
                const data = json.data;
                
                // Show dates checked
                const formattedDates = data.dates.map(d => `${d.substring(0,4)}/${d.substring(4,6)}/${d.substring(6,8)}`);
                instDatesInfo.innerHTML = `<i class="fa-solid fa-clock"></i> <strong>分析區間：</strong>${formattedDates.join(' ➔ ')}`;
                
                // Set Counts
                document.getElementById('count-both-buy').textContent = data.both_buy.length;
                document.getElementById('count-both-sell').textContent = data.both_sell.length;
                document.getElementById('count-foreign-buy').textContent = data.foreign_buy.length;
                document.getElementById('count-foreign-sell').textContent = data.foreign_sell.length;
                document.getElementById('count-sitc-buy').textContent = data.sitc_buy.length;
                document.getElementById('count-sitc-sell').textContent = data.sitc_sell.length;
                
                // Render Both Buy
                renderStreakTable('table-both-buy-body', data.both_buy, true, 'buy');
                // Render Both Sell
                renderStreakTable('table-both-sell-body', data.both_sell, true, 'sell');
                // Render Foreign Buy
                renderStreakTable('table-foreign-buy-body', data.foreign_buy, false, 'buy', 'foreign');
                // Render Foreign Sell
                renderStreakTable('table-foreign-sell-body', data.foreign_sell, false, 'sell', 'foreign');
                // Render SITC Buy
                renderStreakTable('table-sitc-buy-body', data.sitc_buy, false, 'buy', 'sitc');
                // Render SITC Sell
                renderStreakTable('table-sitc-sell-body', data.sitc_sell, false, 'sell', 'sitc');
            } else {
                instDatesInfo.innerHTML = `<span style="color: #f54ea2;"><i class="fa-solid fa-triangle-exclamation"></i> 錯誤: ${json.message}</span>`;
            }
        } catch (err) {
            console.error("Error loading institutional data:", err);
            instDatesInfo.innerHTML = `<span style="color: #f54ea2;"><i class="fa-solid fa-triangle-exclamation"></i> 連線伺服器異常</span>`;
        }
    }

    function renderStreakTable(elementId, list, isBoth, type, forceInst = 'foreign') {
        const tbody = document.getElementById(elementId);
        if (!tbody) return;
        
        if (list.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${isBoth ? 6 : 5}" class="text-center" style="color: #8c82ab;">無符合條件個股</td></tr>`;
            return;
        }

        let html = '';
        list.forEach(r => {
            const marketBadge = `<span style="font-size: 0.75rem; opacity: 0.7; padding: 0.1rem 0.3rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); margin-left: 0.3rem;">${r.market}</span>`;
            const priceVal = r.price !== 'N/A' ? `<strong>${r.price}</strong>` : '<span style="color: #8c82ab;">N/A</span>';
            
            if (isBoth) {
                const fStreakBadge = `<span class="ratio-badge ${type === 'buy' ? 'high' : 'sell-high'}">${r.foreign_streak}日</span>`;
                const sStreakBadge = `<span class="ratio-badge ${type === 'buy' ? 'high' : 'sell-high'}">${r.sitc_streak}日</span>`;
                
                const fValColor = type === 'buy' ? '#00f2fe' : '#f54ea2';
                const sValColor = type === 'buy' ? '#2ecc71' : '#f54ea2';
                const sign = type === 'buy' ? '+' : '';
                
                html += `<tr>
                    <td><strong>${r.code}</strong> <span style="color: #a5a1b8;">${r.name}</span>${marketBadge}</td>
                    <td>${priceVal}</td>
                    <td>${fStreakBadge}</td>
                    <td><span style="color: ${fValColor}; font-weight: 700;">${sign}${r.foreign_sum}</span></td>
                    <td>${sStreakBadge}</td>
                    <td><span style="color: ${sValColor}; font-weight: 700;">${sign}${r.sitc_sum}</span></td>
                </tr>`;
            } else {
                const streak = forceInst === 'foreign' ? r.foreign_streak : r.sitc_streak;
                const latest = forceInst === 'foreign' ? r.foreign_latest : r.sitc_latest;
                const sumVal = forceInst === 'foreign' ? r.foreign_sum : r.sitc_sum;
                
                const streakBadge = `<span class="ratio-badge ${type === 'buy' ? 'high' : 'sell-high'}">${streak}日</span>`;
                const valColor = type === 'buy' ? (forceInst === 'foreign' ? '#3498db' : '#2ecc71') : '#f54ea2';
                const sign = type === 'buy' ? '+' : '';
                
                html += `<tr>
                    <td><strong>${r.code}</strong> <span style="color: #a5a1b8;">${r.name}</span>${marketBadge}</td>
                    <td>${priceVal}</td>
                    <td>${streakBadge}</td>
                    <td><span style="color: ${valColor}; font-weight: 600;">${sign}${latest}</span></td>
                    <td><span style="color: ${valColor}; font-weight: 700;">${sign}${sumVal}</span></td>
                </tr>`;
            }
        });
        tbody.innerHTML = html;
    }

    // Volume Analysis Queries
    const btnVolumeQuery = document.getElementById('btn-volume-query');
    const inputVolumeCode = document.getElementById('volume-query-code');
    const inputVolumeDays = document.getElementById('volume-query-days');
    const blockVolumeResult = document.getElementById('volume-query-result');

    if (btnVolumeQuery) {
        btnVolumeQuery.addEventListener('click', async () => {
            const code = inputVolumeCode.value.trim();
            const days = inputVolumeDays.value;
            if (!code) {
                alert("請輸入股票代號！");
                return;
            }
            
            if (!isLocal) {
                alert("本功能需要使用本地 Python 伺服器進行即時查詢，雲端唯讀網頁暫不支援單股即時均量分析。\n\n請在您本機上執行 python app.py 啟用 Flask 伺服器使用此功能！");
                return;
            }
            
            btnVolumeQuery.disabled = true;
            btnVolumeQuery.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 查詢中`;
            
            try {
                const resp = await fetch(`/api/volume/query?code=${code}&days=${days}`);
                const json = await resp.json();
                
                if (json.status === 'success') {
                    const data = json.data;
                    blockVolumeResult.style.display = 'block';
                    
                    document.getElementById('vq-stock-title').textContent = `${data.name} (${data.code})`;
                    document.getElementById('vq-date-badge').textContent = data.date;
                    document.getElementById('vq-price').textContent = data.price;
                    document.getElementById('vq-volume').textContent = `${data.volume} 張`;
                    document.getElementById('vq-avg-volume').textContent = `${data.avg_volume} 張`;
                    
                    const ratioEl = document.getElementById('vq-ratio');
                    ratioEl.textContent = `${data.ratio}x`;
                    ratioEl.className = 'metric-value';
                    if (data.ratio >= 2.0) {
                        ratioEl.style.color = '#00f2fe';
                    } else if (data.ratio >= 1.2) {
                        ratioEl.style.color = '#f39c12';
                    } else {
                        ratioEl.style.color = '#fff';
                    }
                    
                    // History table
                    let histHtml = '';
                    data.history.forEach(h => {
                        let ratioClass = 'low';
                        if (h.ratio >= 2.0) ratioClass = 'high';
                        else if (h.ratio >= 1.2) ratioClass = 'medium';
                        
                        histHtml += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
                            <td style="padding: 0.5rem 0.3rem;">${h.date}</td>
                            <td style="padding: 0.5rem 0.3rem;"><strong>${h.price}</strong></td>
                            <td style="padding: 0.5rem 0.3rem; color: #e5e1f4;">${h.volume}</td>
                            <td style="padding: 0.5rem 0.3rem; color: #8c82ab;">${h.avg_volume}</td>
                            <td style="padding: 0.5rem 0.3rem;"><span class="ratio-badge ${ratioClass}">${h.ratio}x</span></td>
                        </tr>`;
                    });
                    document.getElementById('vq-history-body').innerHTML = histHtml;
                } else {
                    alert(`錯誤: ${json.message}`);
                }
            } catch (err) {
                console.error("Error querying single stock volume:", err);
                alert("查詢失敗，請檢查網路或稍後再試。");
            } finally {
                btnVolumeQuery.disabled = false;
                btnVolumeQuery.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> 查詢`;
            }
        });
    }

    // Full Market Volume Screener
    const btnVolumeScreen = document.getElementById('btn-volume-screen');
    const selectScreenDays = document.getElementById('volume-screen-days');
    const inputScreenMin = document.getElementById('volume-screen-min');
    const inputScreenRatio = document.getElementById('volume-screen-ratio');
    
    const blockScreenMatches = document.getElementById('volume-screen-matches');
    const textScreenCount = document.getElementById('volume-screen-count');
    const tableScreenBody = document.getElementById('table-volume-screen-body');

    if (btnVolumeScreen) {
        btnVolumeScreen.addEventListener('click', async () => {
            const days = selectScreenDays.value;
            const minVol = inputScreenMin.value;
            const minRatio = inputScreenRatio.value;
            
            btnVolumeScreen.disabled = true;
            btnVolumeScreen.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> 篩選中...`;
            tableScreenBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 2rem 0;"><i class="fa-solid fa-spinner fa-spin"></i> 正在下載全市場資料並計算均量 (約需 15 秒)...</td></tr>`;
            blockScreenMatches.style.display = 'none';

            try {
                let json;
                if (isLocal) {
                    const resp = await fetch(`/api/volume/screener?days=${days}&min_volume=${minVol}&min_ratio=${minRatio}`);
                    json = await resp.json();
                } else {
                    const resp = await fetch(`../data/volume_screener_${days}.json`);
                    const rawJson = await resp.json();
                    
                    if (rawJson.status === 'success') {
                        const rawList = rawJson.data || [];
                        const filtered = rawList.filter(s => {
                            const vol = parseInt(s.volume) || 0;
                            const ratio = parseFloat(s.ratio) || 0;
                            return vol >= minVol && ratio >= minRatio;
                        });
                        json = { status: 'success', data: filtered };
                    } else {
                        json = rawJson;
                    }
                }
                
                if (json.status === 'success') {
                    const list = json.data;
                    blockScreenMatches.style.display = 'block';
                    textScreenCount.textContent = list.length;
                    
                    if (list.length === 0) {
                        tableScreenBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 2rem 0; color: #a5a1b8;">在指定條件下未找到量能爆發的個股</td></tr>`;
                        return;
                    }
                    
                    let html = '';
                    list.forEach(s => {
                        let ratioClass = 'low';
                        if (s.ratio >= 2.0) ratioClass = 'high';
                        else if (s.ratio >= 1.5) ratioClass = 'medium';
                        
                        html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05); text-align: left;">
                            <td style="padding: 0.6rem 0.4rem;"><strong>${s.code}</strong> <span style="color: #a5a1b8;">${s.name}</span> <span style="font-size: 0.75rem; opacity: 0.7; padding: 0.1rem 0.3rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); margin-left: 0.3rem;">${s.market}</span></td>
                            <td style="padding: 0.6rem 0.4rem;"><strong>${s.price}</strong></td>
                            <td style="padding: 0.6rem 0.4rem; color: #00f2fe; font-weight: 600;">${s.volume}</td>
                            <td style="padding: 0.6rem 0.4rem; color: #a5a1b8;">${s.avg_volume}</td>
                            <td style="padding: 0.6rem 0.4rem;"><span class="ratio-badge ${ratioClass}">${s.ratio}x</span></td>
                        </tr>`;
                    });
                    tableScreenBody.innerHTML = html;
                } else {
                    tableScreenBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 2rem 0; color: #f54ea2;"><i class="fa-solid fa-triangle-exclamation"></i> 錯誤: ${json.message}</td></tr>`;
                }
            } catch (err) {
                console.error("Error screening volume:", err);
                tableScreenBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 2rem 0; color: #f54ea2;"><i class="fa-solid fa-triangle-exclamation"></i> 連線伺服器異常</td></tr>`;
            } finally {
                btnVolumeScreen.disabled = false;
                btnVolumeScreen.innerHTML = `<i class="fa-solid fa-bolt"></i> 執行篩選`;
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

    // =========================================================================
    // MARGIN DIAGNOSTICS KANBAN DATA LOADING
    // =========================================================================
    async function loadLatestMarginDiag() {
        const infoEl = document.getElementById('margin-diag-date-info');
        const listSqueeze = document.getElementById('list-squeeze');
        const listMajor = document.getElementById('list-major');
        const listRetail = document.getElementById('list-retail');
        
        const countSqueeze = document.getElementById('count-squeeze');
        const countMajor = document.getElementById('count-major');
        const countRetail = document.getElementById('count-retail');

        if (infoEl) infoEl.textContent = "🔍 正在載入最新數據...";

        try {
            // 1. 取得歷史選股列表，找出最新的籌碼報告
            const response = await fetch(isLocal ? '/api/history' : '../data/history_index.json');
            const history = await response.json();
            
            const latestMargin = history.find(item => item.strategy_type === 'margin');
            
            if (!latestMargin) {
                if (infoEl) infoEl.textContent = "⚠️ 目前無資券籌碼分析報告。";
                [listSqueeze, listMajor, listRetail].forEach(el => {
                    if (el) el.innerHTML = `<div class="text-center" style="color: #8c82ab; padding: 2rem 0;">無符合條件個股</div>`;
                });
                [countSqueeze, countMajor, countRetail].forEach(el => { if (el) el.textContent = '0'; });
                return;
            }

            if (infoEl) infoEl.innerHTML = `<i class="fa-solid fa-clock"></i> <strong>報告日期：</strong>${latestMargin.date}`;

            // 2. 獲取該報表的詳細內容
            let data = [];
            if (isLocal) {
                const reportResp = await fetch(`/api/report/${latestMargin.filename}`);
                data = await reportResp.json();
            } else {
                const reportResp = await fetch(`../data/${latestMargin.filename}`);
                const csvText = await reportResp.text();
                data = parseCSV(csvText);
            }

            // 3. 分類過濾
            const squeezeStocks = [];
            const majorStocks = [];
            const retailStocks = [];

            data.forEach(r => {
                const isSqueeze = r.is_squeeze === true || String(r.is_squeeze).toLowerCase() === 'true';
                const isMajor = r.is_major_fire === true || String(r.is_major_fire).toLowerCase() === 'true';
                const isRetail = r.is_retail_trap === true || String(r.is_retail_trap).toLowerCase() === 'true';

                if (isSqueeze) squeezeStocks.push(r);
                if (isMajor) majorStocks.push(r);
                if (isRetail) retailStocks.push(r);
            });

            // 4. 更新數量
            if (countSqueeze) countSqueeze.textContent = squeezeStocks.length;
            if (countMajor) countMajor.textContent = majorStocks.length;
            if (countRetail) countRetail.textContent = retailStocks.length;

            // 5. 渲染列表
            renderMarginDiagList(listSqueeze, squeezeStocks, 'squeeze');
            renderMarginDiagList(listMajor, majorStocks, 'major');
            renderMarginDiagList(listRetail, retailStocks, 'retail');

        } catch (err) {
            console.error("Error loading latest margin diagnostics:", err);
            if (infoEl) infoEl.innerHTML = `<span style="color: #f54ea2;"><i class="fa-solid fa-triangle-exclamation"></i> 連線伺服器異常</span>`;
        }
    }

    function renderMarginDiagList(container, stocks, type) {
        if (!container) return;
        if (stocks.length === 0) {
            container.innerHTML = `<div class="text-center" style="color: #8c82ab; padding: 2rem 0;">無符合條件個股</div>`;
            return;
        }

        let html = '';
        stocks.forEach(r => {
            const marketBadge = `<span style="font-size: 0.7rem; opacity: 0.7; padding: 0.1rem 0.3rem; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); margin-left: 0.3rem;">${r.市場 || r.market || 'TSE'}</span>`;
            
            // Format margin/short change strings
            let mChange = parseInt(r.今日融資增減) || 0;
            let sChange = parseInt(r.今日融券增減) || 0;
            const mChangeStr = mChange >= 0 ? `+${mChange}` : `${mChange}`;
            const sChangeStr = sChange >= 0 ? `+${sChange}` : `${sChange}`;

            const mColor = mChange >= 0 ? '#ff4757' : '#2ed573';
            const sColor = sChange >= 0 ? '#ff4757' : '#2ed573';

            const price = parseFloat(r.收盤價 || r.選出時收盤價 || 0).toFixed(2);

            html += `
            <div class="stock-item-card" style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px; padding: 0.8rem; transition: transform 0.2s, box-shadow 0.2s; cursor: default;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #fff;">${r.股票代號} ${r.股票名稱}${marketBadge}</span>
                    <span style="font-size: 0.95rem; color: #00f2fe; font-weight: bold;">${price} 元</span>
                </div>
                <div style="display: flex; gap: 0.8rem; flex-wrap: wrap; font-size: 0.8rem; color: #a5a1b8; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 0.4rem; margin-top: 0.4rem;">
                    <span>融資: <strong style="color: ${mColor};">${mChangeStr}</strong></span>
                    <span>融券: <strong style="color: ${sColor};">${sChangeStr}</strong></span>
                    <span>5日量: <strong>${r['5日均量(張)'] || r['5日均量'] || 0}</strong> 張</span>
                </div>
            </div>`;
        });
        container.innerHTML = html;
    }

    // ========================================================
    // 擴充功能控制器：大盤總經風向儀
    // ========================================================
    async function loadMarketCompass() {
        const reportContent = document.getElementById('compass-report-content');
        if (reportContent) reportContent.innerHTML = `📢 正在讀取大盤總經風向儀報告，請稍候...`;

        try {
            // Read from API or JSON static cache depending on env
            let response;
            if (isLocal) {
                response = await fetch('/api/market-compass');
            } else {
                response = await fetch('../data/market_compass.json');
            }
            
            if (response.status === 200) {
                let data;
                if (isLocal) {
                    data = await response.json();
                } else {
                    const metrics = await response.json();
                    // In cloud static pages, we also load the latest report file directly
                    const reportResp = await fetch('../data/reports/market_compass_report_latest.md');
                    const text = reportResp.status === 200 ? await reportResp.text() : "雲端報告加載中，若有延遲請稍後重新整理。";
                    data = { metrics, report: text };
                }
                
                renderMarketCompassMetrics(data.metrics);
                if (reportContent) {
                    reportContent.innerHTML = parseMarkdown(data.report);
                }
            } else {
                if (reportContent) reportContent.innerHTML = `⚠️ 無法加載總經數據，請確認後端服務是否正常。`;
            }
        } catch (err) {
            console.error("Error loading market compass:", err);
            if (reportContent) reportContent.innerHTML = `⚠️ 載入異常: ${err.message}`;
        }
    }

    function renderMarketCompassMetrics(m) {
        if (!m) return;
        
        // 1. Margin Ratio (融資維持率)
        const marginEl = document.getElementById('ind-margin-ratio');
        if (marginEl) {
            const val = m.margin_ratio || 0;
            const state = val >= 160 ? 'safe' : val >= 140 ? 'warn' : 'danger';
            const diagText = val >= 160 ? '🟢 安全偏多' : val >= 140 ? '🟡 融資警戒' : '🔴 恐慌斷頭買點';
            marginEl.className = `indicator-card ${state}`;
            marginEl.innerHTML = `
                <div class="indicator-header">大盤融資維持率 <i class="fa-solid fa-scale-balanced"></i></div>
                <div class="indicator-val">${val}%</div>
                <div class="indicator-diag ${state}">${diagText}</div>
                <div style="font-size: 0.75rem; color: #8c82ab; margin-top: 0.2rem;">更新日期: ${m.margin_ratio_date || 'N/A'}</div>
            `;
        }

        // 2. Futures Net Position (外資期貨淨留倉)
        const futuresEl = document.getElementById('ind-futures-pos');
        if (futuresEl) {
            const val = m.futures_net_position || 0;
            const state = val > 10000 ? 'safe' : val < -20000 ? 'danger' : 'neutral';
            const diagText = val > 10000 ? '🟢 偏多進攻' : val < -20000 ? '🔴 偏空避險' : '⚪ 中性觀望';
            futuresEl.className = `indicator-card ${state}`;
            futuresEl.innerHTML = `
                <div class="indicator-header">外資期貨淨留倉 <i class="fa-solid fa-arrow-trend-up"></i></div>
                <div class="indicator-val">${val.toLocaleString()} 口</div>
                <div class="indicator-diag ${state}">${diagText}</div>
                <div style="font-size: 0.75rem; color: #8c82ab; margin-top: 0.2rem;">更新日期: ${m.futures_date || 'N/A'}</div>
            `;
        }

        // 3. USD/TWD Exchange Rate (新台幣匯率)
        const usdTwdEl = document.getElementById('ind-usd-twd');
        if (usdTwdEl) {
            const val = m.usd_twd || 32.5;
            const state = val > 32.5 ? 'danger' : val < 31.8 ? 'safe' : 'neutral';
            const diagText = val > 32.5 ? '🔴 貶值外資流出' : val < 31.8 ? '🟢 升值外資匯入' : '⚪ 台幣整理';
            usdTwdEl.className = `indicator-card ${state}`;
            usdTwdEl.innerHTML = `
                <div class="indicator-header">新台幣/美元匯率 <i class="fa-solid fa-money-bill-transfer"></i></div>
                <div class="indicator-val">${val}</div>
                <div class="indicator-diag ${state}">${diagText}</div>
                <div style="font-size: 0.75rem; color: #8c82ab; margin-top: 0.2rem;">更新頻率: 盤後每日</div>
            `;
        }

        // 4. NDC Business Cycle Score/Light (景氣燈號與分數)
        const ndcEl = document.getElementById('ind-ndc-score');
        if (ndcEl) {
            const score = m.ndc_score || 0;
            const light = m.ndc_light || 'N/A';
            const state = ['紅', '黃紅'].includes(light) ? 'danger' : ['藍', '黃藍'].includes(light) ? 'safe' : 'neutral';
            const diagText = `${light}燈 (${state === 'danger' ? '🔴 過熱保守' : state === 'safe' ? '🟢 偏冷長買' : '⚪ 穩定'})`;
            ndcEl.className = `indicator-card ${state}`;
            ndcEl.innerHTML = `
                <div class="indicator-header">國發會景氣燈號 <i class="fa-solid fa-lightbulb"></i></div>
                <div class="indicator-val">${score} 分</div>
                <div class="indicator-diag ${state}">${diagText}</div>
                <div style="font-size: 0.75rem; color: #8c82ab; margin-top: 0.2rem;">更新月份: ${m.ndc_date || 'N/A'}</div>
            `;
        }

        // 5. US 10Y Yield (美債 10Y 殖利率)
        const us10yEl = document.getElementById('ind-us-10y');
        if (us10yEl) {
            const val = m.us_10y_yield || 4.0;
            const state = val > 4.3 ? 'danger' : val < 3.8 ? 'safe' : 'neutral';
            const diagText = val > 4.3 ? '🔴 利率高企壓抑' : val < 3.8 ? '🟢 利率舒緩有利' : '⚪ 區間整理';
            us10yEl.className = `indicator-card ${state}`;
            us10yEl.innerHTML = `
                <div class="indicator-header">美債 10Y 殖利率 <i class="fa-solid fa-percent"></i></div>
                <div class="indicator-val">${val}%</div>
                <div class="indicator-diag ${state}">${diagText}</div>
                <div style="font-size: 0.75rem; color: #8c82ab; margin-top: 0.2rem;">更新頻率: 盤後每日</div>
            `;
        }
    }

    async function runMarketCompassCrawler() {
        const btn = document.getElementById('btn-run-compass-crawler');
        if (!btn) return;
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 正在爬取更新中...`;
        
        try {
            const response = await fetch('/api/market-compass/run', { method: 'POST' });
            const res = await response.json();
            alert(res.message || "爬取任務已啟動！請稍後刷新。");
            // Wait 6 seconds and reload compass
            setTimeout(() => {
                loadMarketCompass();
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-play"></i> 手動爬取新數據`;
            }, 6000);
        } catch (err) {
            alert(`手動爬取失敗: ${err.message}`);
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-play"></i> 手動爬取新數據`;
        }
    }

    // ========================================================
    // 擴充功能控制器：黑馬籌碼雷達
    // ========================================================
    let chipHorseData = []; // Store currently loaded list for Modal diagnostics lookup
    
    async function loadChipHorse() {
        const tableBody = document.getElementById('table-chip-horse-body');
        const dateBadge = document.getElementById('chip-horse-date-badge');
        
        if (tableBody) tableBody.innerHTML = `<tr><td colspan="11" class="text-center" style="padding: 2rem 0;"><i class="fa-solid fa-spinner fa-spin"></i> 正在載入黑馬籌碼名單...</td></tr>`;
        
        try {
            let response;
            if (isLocal) {
                response = await fetch('/api/chip-horse');
            } else {
                response = await fetch('../data/chip_horse_latest.json');
            }
            
            if (response.status === 200) {
                const data = await response.json();
                chipHorseData = data.candidates || [];
                
                if (dateBadge) dateBadge.textContent = `數據日期: ${data.date ? data.date.replace(/(\d{4})(\d{2})(\d{2})/, '$1/$2/$3') : 'N/A'}`;
                
                renderChipHorseTable(chipHorseData);
            } else {
                if (tableBody) tableBody.innerHTML = `<tr><td colspan="11" class="text-center" style="color: #f54ea2;">⚠️ 無法載入籌碼雷達名單，請確認數據已生成。</td></tr>`;
            }
        } catch (err) {
            console.error("Error loading chip horse:", err);
            if (tableBody) tableBody.innerHTML = `<tr><td colspan="11" class="text-center" style="color: #f54ea2;">⚠️ 連線異常: ${err.message}</td></tr>`;
        }
    }

    function renderChipHorseTable(list) {
        const tableBody = document.getElementById('table-chip-horse-body');
        if (!tableBody) return;
        
        if (list.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="11" class="text-center" style="padding: 2rem 0; color: #a5a1b8;">本期沒有符合篩選條件的黑馬股</td></tr>`;
            return;
        }
        
        let html = '';
        list.forEach((c, idx) => {
            const largeStreakText = `${c.w0_large}% <span style="font-size: 0.75rem; color:#8c82ab;">← ${c.w1_large}% ← ${c.w2_large}%</span>`;
            const retailStreakText = `${c.w0_retail}% <span style="font-size: 0.75rem; color:#8c82ab;">← ${c.w1_retail}% ← ${c.w2_retail}%</span>`;
            const countStreakText = `${c.w0_shareholders.toLocaleString()} <span style="font-size: 0.75rem; color:#8c82ab;">← ${c.w1_shareholders.toLocaleString()} ← ${c.w2_shareholders.toLocaleString()}</span>`;
            
            // Format delta percentages
            const largeDiffStr = c.large_diff_2w >= 0 ? `+${c.large_diff_2w}%` : `${c.large_diff_2w}%`;
            const countDiffStr = c.shareholders_diff_2w.toLocaleString();
            
            const largeColor = c.large_diff_2w >= 0 ? '#ff4757' : '#2ed573';
            const countColor = c.shareholders_diff_2w <= 0 ? '#2ed573' : '#ff4757';
            
            const foreignStreak = c.foreign_buy_days > 0 ? `<span style="color: #3498db; font-weight:bold;">外:${c.foreign_buy_days}日</span>` : '';
            const sitcStreak = c.sitc_buy_days > 0 ? `<span style="color: #2ecc71; font-weight:bold;">投:${c.sitc_buy_days}日</span>` : '';
            const streakCombo = [foreignStreak, sitcStreak].filter(x => x !== '').join(' / ') || '<span style="color: #8c82ab;">無連買</span>';
            
            const rating = c.ai_diagnosis ? c.ai_diagnosis.rating : '中立';
            const targetPrice = c.ai_diagnosis ? c.ai_diagnosis.target_price : 'N/A';
            const ratingColor = ['買進', '強力買進'].includes(rating) ? '#2ecc71' : '#a5a1b8';
            
            html += `
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.04);">
                <td><strong>${c.code}</strong></td>
                <td><strong>${c.name}</strong></td>
                <td style="color: #00f2fe; font-weight:bold;">${c.current_price || '--'} 元</td>
                <td>${largeStreakText}</td>
                <td style="color: ${largeColor}; font-weight:bold;">${largeDiffStr}</td>
                <td>${retailStreakText}</td>
                <td>${countStreakText}</td>
                <td style="color: ${countColor}; font-weight:bold;">${countDiffStr}</td>
                <td>${streakCombo}</td>
                <td><span style="color: ${ratingColor}; font-weight:bold;">${rating}</span> (目標: ${targetPrice}元)</td>
                <td>
                    <div style="display:flex; gap:0.4rem;">
                        <button class="btn btn-primary" onclick="showDiagModal('${c.code}')" style="padding: 0.2rem 0.5rem; font-size:0.75rem; height:24px;">
                            <i class="fa-solid fa-brain"></i> AI診斷
                        </button>
                        <button class="btn btn-long" onclick="jumpToTechnicalAnalysis('${c.code}')" style="padding: 0.2rem 0.5rem; font-size:0.75rem; height:24px; background: rgba(0, 242, 254, 0.1); border: 1px solid rgba(0, 242, 254, 0.2); color: #00f2fe;">
                            <i class="fa-solid fa-chart-line"></i> 線圖
                        </button>
                    </div>
                </td>
            </tr>`;
        });
        tableBody.innerHTML = html;
    }

    window.showDiagModal = function(code) {
        const item = chipHorseData.find(c => c.code === code);
        if (!item) return;
        
        const overlay = document.getElementById('modal-diagnosis-overlay');
        const title = document.getElementById('modal-diag-title');
        const body = document.getElementById('modal-diag-body');
        
        if (title) title.innerHTML = `<i class="fa-solid fa-horse-head" style="color: #f39c12; margin-right:0.5rem;"></i> 黑馬診斷：${item.name} (${item.code})`;
        
        const diag = item.ai_diagnosis || { rating: '中立', target_price: 'N/A', key_reasons: ['籌碼面呈大戶緩增，浮額逐漸洗淨'], risk_note: '短期面臨大盤波動風險，建議逢回分批承接。' };
        
        let reasonsHtml = '';
        diag.key_reasons.forEach(r => {
            reasonsHtml += `<li style="margin-bottom:0.5rem; color:#d1cbe5;">${r}</li>`;
        });
        
        if (body) {
            body.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center; background: rgba(255,255,255,0.03); padding:1rem; border-radius:10px; border:1px solid rgba(255,255,255,0.05); margin-bottom:1.5rem;">
                    <div>
                        <span style="font-size:0.85rem; color:#8c82ab; display:block;">分析師評等</span>
                        <strong style="font-size:1.4rem; color:#2ecc71; font-weight:700;">${diag.rating}</strong>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.85rem; color:#8c82ab; display:block;">合理估計目標價</span>
                        <strong style="font-size:1.4rem; color:#00f2fe; font-weight:700;">${diag.target_price} 元</strong>
                    </div>
                </div>
                
                <h4 style="color:#fff; margin-bottom:0.8rem; font-size:1.05rem; display:flex; align-items:center; gap:0.4rem;"><i class="fa-solid fa-list-check" style="color:#00f2fe;"></i> 核心看好理由</h4>
                <ul style="padding-left:1.2rem; margin-bottom:1.5rem;">
                    ${reasonsHtml}
                </ul>
                
                <h4 style="color:#fff; margin-bottom:0.5rem; font-size:1.05rem; display:flex; align-items:center; gap:0.4rem;"><i class="fa-solid fa-triangle-exclamation" style="color:#ffa502;"></i> 潛在風險提示</h4>
                <div style="background: rgba(243, 156, 18, 0.05); border-left: 4px solid #ffa502; padding:0.8rem 1rem; border-radius: 0 8px 8px 0; color:#d1cbe5; font-size:0.9rem; line-height:1.6;">
                    ${diag.risk_note}
                </div>
                
                <div style="margin-top:2rem; display:flex; justify-content:flex-end;">
                    <button class="btn btn-long" onclick="jumpToTechnicalAnalysis('${item.code}'); closeDiagModal();" style="background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%); color:#0b0813; font-weight:700; border:none; padding:0.6rem 1.5rem; border-radius:8px; cursor:pointer;">
                        📈 帶入波段線圖進行交易
                    </button>
                </div>
            `;
        }
        
        if (overlay) overlay.classList.add('active');
    };

    window.closeDiagModal = function() {
        const overlay = document.getElementById('modal-diagnosis-overlay');
        if (overlay) overlay.classList.remove('active');
    };
    
    // Wire modal close actions
    const modalCloseBtn = document.getElementById('modal-diag-close-btn');
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', closeDiagModal);
    }
    const modalOverlay = document.getElementById('modal-diagnosis-overlay');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeDiagModal();
        });
    }

    window.jumpToTechnicalAnalysis = function(code) {
        // Find buttons
        const instTabBtn = document.querySelector('.tab-btn[data-tab="institutional"]');
        const instVolumeSubTabBtn = document.querySelector('.sub-tab-btn[data-sub-tab="inst-volume-panel"]');
        const queryInput = document.getElementById('volume-query-code');
        const queryBtn = document.getElementById('btn-volume-query');
        
        // 1. Switch to institutional Tab
        if (instTabBtn) instTabBtn.click();
        
        // 2. Switch to Volume sub-tab
        if (instVolumeSubTabBtn) instVolumeSubTabBtn.click();
        
        // 3. Set input value
        if (queryInput) queryInput.value = code;
        
        // 4. Trigger search
        if (queryBtn) {
            setTimeout(() => {
                queryBtn.click();
            }, 300);
        }
    };

    async function runChipHorseCrawler() {
        const btn = document.getElementById('btn-run-chip-horse-crawler');
        if (!btn) return;
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 正在篩選中...`;
        
        try {
            const response = await fetch('/api/chip-horse/run', { method: 'POST' });
            const res = await response.json();
            alert(res.message || "篩選任務已啟動！可能需要 20-30 秒下載最新集保與現價資料，請稍候。");
            
            // Wait 25 seconds and reload
            setTimeout(() => {
                loadChipHorse();
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-play"></i> 手動下載篩選 (每週六)`;
            }, 25000);
        } catch (err) {
            alert(`篩選任務啟動失敗: ${err.message}`);
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-play"></i> 手動下載篩選 (每週六)`;
        }
    }

    // ========================================================
    // 擴充功能控制器：監控警示設定 (Telegram Alerts)
    // ========================================================
    async function loadAlertConfigs() {
        const rulesList = document.getElementById('alert-rules-list');
        if (rulesList) rulesList.innerHTML = `<div class="text-center" style="color: #8c82ab; padding: 2rem 0;"><i class="fa-solid fa-spinner fa-spin"></i> 載入監控規則中...</div>`;
        
        try {
            const response = await fetch('/api/alerts');
            if (response.status === 200) {
                const configs = await response.json();
                renderAlertRules(configs);
            } else {
                if (rulesList) rulesList.innerHTML = `<div class="text-center" style="color: #f54ea2;">⚠️ 載入警示規則失敗，請確認後端服務。</div>`;
            }
        } catch (err) {
            console.error("Error loading alert configs:", err);
            if (rulesList) rulesList.innerHTML = `<div class="text-center" style="color: #f54ea2;">⚠️ 連線異常: ${err.message}</div>`;
        }
    }

    function renderAlertRules(configs) {
        const container = document.getElementById('alert-rules-list');
        if (!container) return;
        
        if (configs.length === 0) {
            container.innerHTML = `<div class="text-center" style="color: #8c82ab; padding: 4rem 0;"><i class="fa-solid fa-bell-slash" style="font-size: 2rem; margin-bottom:1rem; opacity:0.5;"></i><br>目前沒有任何監控規則，請利用左側表單新增自選股監控。</div>`;
            return;
        }
        
        let html = '';
        configs.forEach(c => {
            const conds = c.conditions || {};
            let chipsHtml = '';
            
            if (conds.price_above) chipsHtml += `<span class="cond-chip">📈 破 ${conds.price_above}元</span>`;
            if (conds.price_below) chipsHtml += `<span class="cond-chip">📉 跌破 ${conds.price_below}元</span>`;
            if (conds.inst_buy_above) chipsHtml += `<span class="cond-chip">💼 法人買超 &gt; ${conds.inst_buy_above}張</span>`;
            if (conds.volume_ratio_above) chipsHtml += `<span class="cond-chip">🔥 量比 &gt; ${conds.volume_ratio_above}倍</span>`;
            if (conds.volume_spike_above) chipsHtml += `<span class="cond-chip">⚡ 5m量爆發 &gt; ${conds.volume_spike_above}倍</span>`;
            
            const isChecked = c.is_active !== false ? 'checked' : '';
            
            html += `
            <div class="alert-rule-item">
                <div class="alert-rule-info">
                    <h5><strong>${c.stock_name || '未命名'} (${c.stock_code})</strong></h5>
                    <div class="alert-rule-conds">
                        ${chipsHtml}
                    </div>
                </div>
                <div class="alert-rule-actions">
                    <label class="switch">
                        <input type="checkbox" onchange="toggleAlertRule('${c.id}', this.checked)" ${isChecked}>
                        <span class="slider"></span>
                    </label>
                    <button class="btn-delete-rule" onclick="deleteAlertRule('${c.id}')" title="刪除規則">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>`;
        });
        container.innerHTML = html;
    }

    window.saveAlertRule = async function() {
        const codeInput = document.getElementById('alert-stock-code');
        const nameInput = document.getElementById('alert-stock-name');
        const aboveInput = document.getElementById('alert-price-above');
        const belowInput = document.getElementById('alert-price-below');
        const instInput = document.getElementById('alert-inst-buy');
        const ratioInput = document.getElementById('alert-volume-ratio');
        const spikeInput = document.getElementById('alert-volume-spike');
        
        if (!codeInput || !codeInput.value.trim()) {
            alert("請填寫股票代號！");
            return;
        }
        
        const code = codeInput.value.trim();
        const name = nameInput.value.trim() || `自選股_${code}`;
        
        const conditions = {};
        if (aboveInput.value) conditions.price_above = parseFloat(aboveInput.value);
        if (belowInput.value) conditions.price_below = parseFloat(belowInput.value);
        if (instInput.value) conditions.inst_buy_above = parseInt(instInput.value);
        if (ratioInput.value) conditions.volume_ratio_above = parseFloat(ratioInput.value);
        if (spikeInput && spikeInput.value) conditions.volume_spike_above = parseFloat(spikeInput.value);
        
        if (Object.keys(conditions).length === 0) {
            alert("請至少設定一項監控條件！");
            return;
        }
        
        const newRule = {
            stock_code: code,
            stock_name: name,
            conditions: conditions,
            is_active: true
        };
        
        try {
            const response = await fetch('/api/alerts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newRule)
            });
            
            if (response.status === 200) {
                alert("自選監控警示規則新增成功！");
                // Clear form
                codeInput.value = '';
                nameInput.value = '';
                aboveInput.value = '';
                belowInput.value = '';
                instInput.value = '';
                ratioInput.value = '';
                if (spikeInput) spikeInput.value = '';
                // Reload list
                loadAlertConfigs();
            } else {
                alert("新增失敗，請確認後端連線。");
            }
        } catch (err) {
            alert(`連線異常: ${err.message}`);
        }
    };

    window.toggleAlertRule = async function(id, isChecked) {
        try {
            // Get original rule
            const getResp = await fetch('/api/alerts');
            const configs = await getResp.json();
            const rule = configs.find(c => c.id === id);
            if (!rule) return;
            
            rule.is_active = isChecked;
            
            await fetch('/api/alerts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rule)
            });
            console.log(`Rule ${id} toggled active state: ${isChecked}`);
        } catch (err) {
            console.error("Error toggling alert rule state:", err);
        }
    };

    window.deleteAlertRule = async function(id) {
        if (!confirm("確定要刪除此條監控規則嗎？")) return;
        try {
            const response = await fetch(`/api/alerts/${id}`, { method: 'DELETE' });
            if (response.status === 200) {
                loadAlertConfigs();
            } else {
                alert("刪除失敗");
            }
        } catch (err) {
            alert(`連線異常: ${err.message}`);
        }
    };

    // ========================================================
    // 輔助工具：簡易 Markdown 渲染器與 Markdown 表格處理
    // ========================================================
    function parseMarkdown(md) {
        if (!md) return "";
        let html = md;
        // Escape HTML entities to prevent rendering issues
        html = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        
        // Blockquotes for alerts (important, tip, warning etc)
        html = html.replace(/^&gt;\s*\[\!IMPORTANT\]\s*([\s\S]*?)(?=\n\n|\n[^\&gt;]|$)/gm, '<blockquote class="important"><strong>⚠️ 重要：</strong><br>$1</blockquote>');
        html = html.replace(/^&gt;\s*\[\!WARNING\]\s*([\s\S]*?)(?=\n\n|\n[^\&gt;]|$)/gm, '<blockquote class="important"><strong>⚠️ 警告：</strong><br>$1</blockquote>');
        html = html.replace(/^&gt;\s*(.*?)(?=\n\n|\n[^\&gt;]|$)/gm, '<blockquote>$1</blockquote>');
        
        // Headers
        html = html.replace(/^#\s+(.*?)$/gm, '<h1>$1</h1>');
        html = html.replace(/^##\s+(.*?)$/gm, '<h2>$1</h2>');
        html = html.replace(/^###\s+(.*?)$/gm, '<h3>$1</h3>');
        
        // Bold
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Lists
        html = html.replace(/^\-\s+(.*?)$/gm, '<li>$1</li>');
        
        // Tables parsing
        let lines = html.split('\n');
        let inTable = false;
        for (let i = 0; i < lines.length; i++) {
            let trimmed = lines[i].trim();
            if (trimmed.startsWith('|')) {
                if (!inTable) {
                    inTable = true;
                    lines[i] = '<table><thead>' + renderTableRow(lines[i], true) + '</thead><tbody>';
                } else if (trimmed.includes('---')) {
                    lines[i] = ''; // Skip divider line
                } else {
                    lines[i] = renderTableRow(lines[i], false);
                }
            } else {
                if (inTable) {
                    inTable = false;
                    lines[i] = '</tbody></table>' + lines[i];
                }
            }
        }
        html = lines.join('\n');
        
        // Clean empty double newlines into spacing
        html = html.replace(/\n\n/g, '<p></p>');
        return html;
    }

    function renderTableRow(line, isHeader) {
        let cells = line.split('|').map(c => c.trim()).filter((c, idx, arr) => idx > 0 && idx < arr.length - 1);
        let tag = isHeader ? 'th' : 'td';
        cells = cells.map(c => c.replace(/^&gt;\s*/, ''));
        return '<tr>' + cells.map(c => `<${tag}>${c}</${tag}>`).join('') + '</tr>';
    }

    // Set up event listener hooks for form and crawler buttons
    const btnCompassRefresh = document.getElementById('btn-refresh-compass');
    if (btnCompassRefresh) btnCompassRefresh.addEventListener('click', loadMarketCompass);
    
    const btnCompassCrawler = document.getElementById('btn-run-compass-crawler');
    if (btnCompassCrawler) {
        if (isLocal) {
            btnCompassCrawler.addEventListener('click', runMarketCompassCrawler);
        } else {
            btnCompassCrawler.style.display = 'none';
        }
    }
    
    const btnChipHorseRefresh = document.getElementById('btn-refresh-chip-horse');
    if (btnChipHorseRefresh) btnChipHorseRefresh.addEventListener('click', loadChipHorse);
    
    const btnChipHorseCrawler = document.getElementById('btn-run-chip-horse-crawler');
    if (btnChipHorseCrawler) {
        if (isLocal) {
            btnChipHorseCrawler.addEventListener('click', runChipHorseCrawler);
        } else {
            btnChipHorseCrawler.style.display = 'none';
        }
    }
    
    const formAddAlert = document.getElementById('form-add-alert');
    if (formAddAlert) {
        formAddAlert.addEventListener('submit', (e) => {
            e.preventDefault();
            saveAlertRule();
        });
    }

    // ========================================================
    // 個股研究加碼評估 UI 控制器
    // ========================================================
    let currentStockData = null;

    async function runStockAnalysis(stockCode) {
        if (!stockCode) {
            alert("請輸入股票代號");
            return;
        }
        
        const panelDashboardGrid = document.getElementById('analysis-dashboard-grid');
        const panelLoading = document.getElementById('analysis-loading-panel');
        const panelReportCard = document.getElementById('analysis-report-card');
        const txtError = document.getElementById('analysis-error-message');
        const lblLoadingStatus = document.getElementById('analysis-loading-status');
        
        txtError.style.display = 'none';
        panelDashboardGrid.style.display = 'none';
        panelReportCard.style.display = 'none';
        panelLoading.style.display = 'block';
        lblLoadingStatus.innerText = '正在透過 Selenium 搜尋觀測站法說會簡報，並獲取估值與營收數據...';
        
        try {
            const res = await fetch(`/api/stock-analysis?code=${stockCode}`);
            const data = await res.json();
            
            if (data.status !== 'success') {
                panelLoading.style.display = 'none';
                txtError.innerText = `分析失敗: ${data.message || '未知錯誤'}`;
                txtError.style.display = 'block';
                return;
            }
            
            currentStockData = data;
            
            document.getElementById('analysis-company-name-title').innerText = `${data.company_name} (${data.stock_code})`;
            
            const currentPrice = data.current_price;
            document.getElementById('analysis-current-price').innerText = currentPrice ? `${currentPrice} 元` : '未提供';
            
            const ratingMap = {
                'strong_buy': { text: '強烈買進', color: '#2ecc71' },
                'buy': { text: '買進', color: '#2ecc71' },
                'hold': { text: '持有', color: '#f1c40f' },
                'sell': { text: '賣出', color: '#e74c3c' },
                'strong_sell': { text: '強烈賣出', color: '#e74c3c' }
            };
            const rInfo = ratingMap[data.rating] || { text: data.rating || '無評等', color: '#8c82ab' };
            const rBadge = document.getElementById('analysis-rating-badge');
            rBadge.innerText = rInfo.text;
            rBadge.style.color = rInfo.color;
            
            document.getElementById('analysis-analysts-count').innerText = `${data.analysts_count} 家`;
            
            const targets = data.price_targets;
            const priceLow = targets.low;
            const priceHigh = targets.high;
            const priceMean = targets.mean;
            
            document.getElementById('analysis-price-low').innerText = priceLow ? `最低: ${priceLow} 元` : '最低: -';
            document.getElementById('analysis-price-high').innerText = priceHigh ? `最高: ${priceHigh} 元` : '最高: -';
            
            if (currentPrice && priceLow && priceHigh) {
                let pct = ((currentPrice - priceLow) / (priceHigh - priceLow)) * 100;
                pct = Math.max(0, Math.min(100, pct));
                document.getElementById('analysis-price-range-fill').style.width = pct + '%';
                document.getElementById('analysis-price-pin').style.left = pct + '%';
            } else {
                document.getElementById('analysis-price-range-fill').style.width = '0%';
                document.getElementById('analysis-price-pin').style.left = '0%';
            }
            
            if (priceMean && currentPrice) {
                const upside = ((priceMean / currentPrice) - 1) * 100;
                const upsideText = upside >= 0 ? `+${upside.toFixed(1)}%` : `${upside.toFixed(1)}%`;
                const upsideClass = upside >= 0 ? 'text-up' : 'text-down';
                document.getElementById('analysis-price-mean-desc').innerHTML = `平均目標價: <span style="color:#fff;">${priceMean.toFixed(1)} 元</span> (潛在空間: <span class="${upsideClass}">${upsideText}</span>)`;
            } else {
                document.getElementById('analysis-price-mean-desc').innerText = '平均目標價: - 元';
            }
            
            const rev = data.revenue;
            document.getElementById('analysis-revenue-ym').innerText = rev.date_ym ? `${rev.date_ym.substring(0, 3)}年${rev.date_ym.substring(3)}月` : '-';
            
            const revValFormatted = rev.monthly_rev ? `${(parseInt(rev.monthly_rev) / 1000).toLocaleString(undefined, {maximumFractionDigits:0})} 千元` : '- 元';
            document.getElementById('analysis-revenue-val').innerText = revValFormatted;
            
            const formatPct = (valStr) => {
                const val = parseFloat(valStr);
                if (isNaN(val)) return '-';
                const cls = val >= 0 ? 'text-up' : 'text-down';
                const sign = val >= 0 ? '+' : '';
                return `<span class="${cls}">${sign}${val.toFixed(2)}%</span>`;
            };
            document.getElementById('analysis-revenue-mom').innerHTML = formatPct(rev.mom);
            document.getElementById('analysis-revenue-yoy').innerHTML = formatPct(rev.yoy);
            document.getElementById('analysis-revenue-ytd-yoy').innerHTML = formatPct(rev.ytd_yoy);
            document.getElementById('analysis-revenue-remark').innerText = rev.remark || '-';
            
            const brief = data.briefing;
            document.getElementById('analysis-briefing-date').innerText = brief.date || '無最近法說會';
            document.getElementById('analysis-briefing-time').innerText = brief.time || '-';
            document.getElementById('analysis-briefing-location').innerText = brief.location || '-';
            
            const pdfEl = document.getElementById('analysis-briefing-pdf');
            if (brief.pdf_filename) {
                pdfEl.innerHTML = `<a href="${brief.pdf_url}" target="_blank" style="color: #a29bfe; text-decoration: underline;"><i class="fa-solid fa-file-pdf"></i> ${brief.pdf_filename}</a>`;
            } else {
                pdfEl.innerText = '無簡報檔案';
            }
            
            const reportsContainer = document.getElementById('analysis-history-reports-container');
            reportsContainer.innerHTML = '';
            if (data.history_reports && data.history_reports.length > 0) {
                data.history_reports.forEach(r => {
                    const div = document.createElement('div');
                    div.className = 'history-report-item';
                    div.innerHTML = `
                        <span><i class="fa-solid fa-file-lines" style="margin-right:0.3rem;"></i> ${r.date} 法說評估報告</span>
                        <i class="fa-solid fa-chevron-right"></i>
                    `;
                    div.addEventListener('click', () => {
                        loadHistoryReportContent(stockCode, r.filename);
                    });
                    reportsContainer.appendChild(div);
                });
            } else {
                reportsContainer.innerHTML = '<div style="font-size:0.8rem; color:#8c82ab; text-align:center; padding:0.5rem;">無歷史報告</div>';
            }
            
            panelLoading.style.display = 'none';
            panelDashboardGrid.style.display = 'flex';
            
            if (data.ai_report_exists && data.ai_report) {
                document.getElementById('analysis-report-body').innerHTML = parseMarkdown(data.ai_report);
                panelReportCard.style.display = 'block';
            } else if (brief.pdf_filename) {
                document.getElementById('analysis-report-body').innerHTML = `
                    <div class="text-center" style="padding: 2rem 0;">
                        <p style="margin-bottom:1rem;">偵測到該個股有最新法說會簡報，但尚未生成 AI 診斷報告。</p>
                        <button class="btn btn-primary" id="btn-generate-initial-report" style="background: linear-gradient(135deg, #00cec9 0%, #0984e3 100%);">
                            <i class="fa-solid fa-wand-magic-sparkles"></i> 立即下載簡報並生成 AI 診斷報告
                        </button>
                    </div>
                `;
                panelReportCard.style.display = 'block';
                document.getElementById('btn-generate-initial-report').addEventListener('click', triggerGenerateReport);
            } else {
                document.getElementById('analysis-report-body').innerHTML = '<div class="text-center" style="padding: 2rem 0; color: #8c82ab;">此個股查無最新法說會簡報 PDF 檔案，無法進行 AI 深度診斷。</div>';
                panelReportCard.style.display = 'block';
            }
            
        } catch (err) {
            panelLoading.style.display = 'none';
            txtError.innerText = `請求異常: ${err.message}`;
            txtError.style.display = 'block';
        }
    }

    async function loadHistoryReportContent(stockCode, filename) {
        const reportBody = document.getElementById('analysis-report-body');
        reportBody.innerHTML = '<div class="text-center" style="padding: 2rem 0;"><div class="loader-spinner" style="border: 3px solid rgba(255,255,255,0.1); border-top: 3px solid #00cec9; border-radius: 50%; width: 25px; height: 25px; animation: spin 1s linear infinite; margin: 0 auto 1rem auto;"></div>正在加載歷史報告內容...</div>';
        document.getElementById('analysis-report-card').style.display = 'block';
        
        try {
            const res = await fetch(`/api/download/reports/${filename}`);
            if (res.status === 200) {
                const text = await res.text();
                reportBody.innerHTML = parseMarkdown(text);
                document.getElementById('analysis-report-card').scrollIntoView({ behavior: 'smooth' });
            } else {
                reportBody.innerHTML = `<div class="text-center text-down" style="padding: 2rem 0;">讀取歷史報告失敗 (HTTP ${res.status})</div>`;
            }
        } catch (err) {
            reportBody.innerHTML = `<div class="text-center text-down" style="padding: 2rem 0;">讀取報告異常: ${err.message}</div>`;
        }
    }

    async function triggerGenerateReport() {
        if (!currentStockData || !currentStockData.briefing.pdf_filename) {
            alert("無法生成報告: 缺少簡報資訊");
            return;
        }
        
        const panelLoading = document.getElementById('analysis-loading-panel');
        const panelReportCard = document.getElementById('analysis-report-card');
        const panelDashboardGrid = document.getElementById('analysis-dashboard-grid');
        const lblLoadingStatus = document.getElementById('analysis-loading-status');
        
        panelDashboardGrid.style.display = 'none';
        panelReportCard.style.display = 'none';
        panelLoading.style.display = 'block';
        lblLoadingStatus.innerText = '正在下載法說會簡報 PDF，抽取關鍵內容並發送至 Gemini 生成深度評估報告 (大約需要 15~20 秒)...';
        
        const code = currentStockData.stock_code;
        const payload = {
            code: code,
            pdf_url: currentStockData.briefing.pdf_url,
            pdf_filename: currentStockData.briefing.pdf_filename,
            date: currentStockData.briefing.date,
            context: {
                company_name: currentStockData.company_name,
                current_price: currentStockData.current_price || 'N/A',
                price_low: currentStockData.price_targets.low || 'N/A',
                price_mean: currentStockData.price_targets.mean || 'N/A',
                price_high: currentStockData.price_targets.high || 'N/A',
                revenue_val: currentStockData.revenue.monthly_rev || 'N/A',
                revenue_mom: currentStockData.revenue.mom || 'N/A',
                revenue_yoy: currentStockData.revenue.yoy || 'N/A',
                revenue_ytd_yoy: currentStockData.revenue.ytd_yoy || 'N/A',
                revenue_remark: currentStockData.revenue.remark || '無'
            }
        };
        
        try {
            const res = await fetch('/api/stock-analysis/ai-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            if (data.status !== 'success') {
                panelLoading.style.display = 'none';
                alert(`生成報告失敗: ${data.message}`);
                panelDashboardGrid.style.display = 'flex';
                return;
            }
            
            await runStockAnalysis(code);
        } catch (err) {
            panelLoading.style.display = 'none';
            alert(`請求生成報告異常: ${err.message}`);
            panelDashboardGrid.style.display = 'flex';
        }
    }

    // Hook up elements
    const btnRunAnalysis = document.getElementById('btn-run-analysis');
    const inputStockCode = document.getElementById('analysis-stock-code');
    const btnRegenerateAiReport = document.getElementById('btn-regenerate-ai-report');

    if (btnRunAnalysis) {
        btnRunAnalysis.addEventListener('click', () => {
            runStockAnalysis(inputStockCode.value.trim());
        });
    }

    if (inputStockCode) {
        inputStockCode.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                runStockAnalysis(inputStockCode.value.trim());
            }
        });
    }

    if (btnRegenerateAiReport) {
        btnRegenerateAiReport.addEventListener('click', triggerGenerateReport);
    }

    checkStatusOnLoad();
    
    // Auto-load margin diagnostics and initial compass load
    loadLatestMarginDiag();
    
    // If the window URL points to specific tab, let's load it
    // Wait, the switcher handles tab click. Let's do a default trigger if page load matches any.
});
