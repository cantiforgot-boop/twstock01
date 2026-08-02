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

    checkStatusOnLoad();
    
    // Auto-load margin diagnostics if initial tab is selected (or when switching)
    // We already handle it on tab click.
    
    // Also run loadLatestMarginDiag initially if needed
    loadLatestMarginDiag();
});
