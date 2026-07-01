// Global application state
let cohortDataset = null;
let currentViewMode = 'percentage'; // 'percentage' or 'count'
let decayChartInstance = null;
let trendsChartInstance = null;

// Initialize Lucide icons on page load
document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    loadDashboardData();
    setupEventListeners();
});

// Event Listeners for Heatmap toggles
function setupEventListeners() {
    const btnPercent = document.getElementById('toggle-percent');
    const btnCount = document.getElementById('toggle-count');

    btnPercent.addEventListener('click', () => {
        if (currentViewMode !== 'percentage') {
            currentViewMode = 'percentage';
            btnPercent.classList.add('active');
            btnCount.classList.remove('active');
            renderCohortHeatmap();
        }
    });

    btnCount.addEventListener('click', () => {
        if (currentViewMode !== 'count') {
            currentViewMode = 'count';
            btnCount.classList.add('active');
            btnPercent.classList.remove('active');
            renderCohortHeatmap();
        }
    });
}

// Asynchronously load the JSON analytical data
async function loadDashboardData() {
    try {
        const response = await fetch('cohort_data.json');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        cohortDataset = await response.json();
        
        // Populate dashboard components
        populateKPIs(cohortDataset.kpis);
        renderCohortHeatmap();
        renderDecayChart();
        renderMonthlyTrendsChart();
        populateCategoryTable(cohortDataset.category_performance);
        populateGeoTable(cohortDataset.geo_distribution);
        
    } catch (error) {
        console.error("Failed to load cohort dashboard data:", error);
        document.getElementById('cohort-heatmap').innerHTML = `
            <div class="loading-spinner" style="color: var(--danger)">
                <i data-lucide="alert-circle" style="margin-bottom: 0.5rem; display: inline-block;"></i>
                <p>Failed to load cohort data. Make sure you have executed 'cohort_analysis.py' first.</p>
            </div>
        `;
        lucide.createIcons();
    }
}

// Format numbers nicely
function formatCurrency(value) {
    if (value >= 1e6) {
        return `$${(value / 1e6).toFixed(2)}M`;
    }
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}

function formatNumber(value) {
    return new Intl.NumberFormat('en-US').format(value);
}

// Populate the KPI summary cards
function populateKPIs(kpis) {
    document.getElementById('kpi-customers').innerText = formatNumber(kpis.total_customers);
    document.getElementById('kpi-retention').innerText = `${kpis.avg_month_1_retention.toFixed(2)}%`;
    document.getElementById('kpi-revenue').innerText = formatCurrency(kpis.total_revenue);
    document.getElementById('kpi-aov').innerText = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(kpis.overall_aov);
}

// Custom HSL purple scale for Olist retention cells (highly customized for low numbers)
function getCellBackgroundColor(percentage) {
    if (percentage === 0) return 'rgba(147, 51, 234, 0.05)';
    if (percentage > 0 && percentage < 0.5) return 'rgba(147, 51, 234, 0.2)';
    if (percentage >= 0.5 && percentage < 1.0) return 'rgba(147, 51, 234, 0.4)';
    if (percentage >= 1.0 && percentage < 2.0) return 'rgba(147, 51, 234, 0.65)';
    if (percentage >= 2.0 && percentage < 3.0) return 'rgba(147, 51, 234, 0.85)';
    return 'rgba(147, 51, 234, 1.0)'; // Strong purple for >3%
}

// Render the Cohort Heatmap grid
function renderCohortHeatmap() {
    const container = document.getElementById('cohort-heatmap');
    if (!cohortDataset || !cohortDataset.cohorts) return;

    const cohorts = cohortDataset.cohorts;
    const maxMonths = 12; // Track Month 0 to Month 12

    // Create table structure
    let html = `
        <table class="heatmap-table">
            <thead>
                <tr>
                    <th>Cohort Month</th>
                    <th>Cohort Size</th>
    `;

    // Add Month headers
    for (let i = 0; i <= maxMonths; i++) {
        html += `<th>Month ${i}</th>`;
    }
    
    html += `
                </tr>
            </thead>
            <tbody>
    `;

    // Generate rows
    cohorts.forEach(cohort => {
        // Skip cohorts with sizes that are too small or incomplete at start (e.g. 2016-09 has 1 customer)
        if (cohort.cohort_size < 50) return;

        html += `
            <tr>
                <td><strong>${cohort.cohort_month}</strong></td>
                <td>${formatNumber(cohort.cohort_size)}</td>
        `;

        for (let i = 0; i <= maxMonths; i++) {
            const retentionData = cohort.retention[i];
            
            if (retentionData !== undefined) {
                const pct = retentionData.percentage;
                const cnt = retentionData.count;
                const bg = getCellBackgroundColor(pct);
                const val = currentViewMode === 'percentage' ? `${pct.toFixed(2)}%` : formatNumber(cnt);

                // Add heatmap cell with custom inline color
                html += `
                    <td class="heatmap-cell" style="background-color: ${bg};" title="Cohort: ${cohort.cohort_month} | Period: Month ${i}\nCustomers: ${formatNumber(cnt)} | Retention: ${pct.toFixed(2)}%">
                        ${val}
                    </td>
                `;
            } else {
                // Future periods with no data
                html += `<td style="background-color: rgba(255,255,255,0.02); color: var(--text-muted); font-size: 0.7rem;">-</td>`;
            }
        }
        
        html += `</tr>`;
    });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

// Render Cohort Churn Decay Curve (Line Chart)
function renderDecayChart() {
    const ctx = document.getElementById('retentionDecayChart').getContext('2d');
    if (!cohortDataset || !cohortDataset.cohorts) return;

    // We select 3 representative cohorts with good historical runtime to compare
    const targetCohorts = ['2017-01', '2017-06', '2017-11'];
    const datasets = [];
    const colors = [
        { border: '#a855f7', bg: 'rgba(168, 85, 247, 0.1)' },
        { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)' },
        { border: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' }
    ];

    let colorIdx = 0;
    targetCohorts.forEach(cohortMonth => {
        const cohort = cohortDataset.cohorts.find(c => c.cohort_month === cohortMonth);
        if (!cohort) return;

        const dataPoints = [];
        // Extract Month 1 to 12 retention percentage (Month 0 is always 100%, exclude for zoom scaling)
        for (let i = 1; i <= 12; i++) {
            const retention = cohort.retention[i];
            dataPoints.push(retention ? retention.percentage : null);
        }

        datasets.push({
            label: `Cohort ${cohortMonth}`,
            data: dataPoints,
            borderColor: colors[colorIdx].border,
            backgroundColor: colors[colorIdx].bg,
            borderWidth: 3,
            pointRadius: 4,
            pointBackgroundColor: colors[colorIdx].border,
            tension: 0.35,
            fill: false
        });
        colorIdx++;
    });

    if (decayChartInstance) decayChartInstance.destroy();

    decayChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array.from({ length: 12 }, (_, i) => `Month ${i + 1}`),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#f3f4f6', font: { family: 'Outfit', weight: 600 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Outfit' } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { 
                        color: '#9ca3af', 
                        font: { family: 'Outfit' },
                        callback: function(value) { return value.toFixed(1) + '%'; }
                    },
                    suggestedMax: 2.5
                }
            }
        }
    });
}

// Render Monthly Active Customers & Revenue Trends
function renderMonthlyTrendsChart() {
    const ctx = document.getElementById('monthlyTrendsChart').getContext('2d');
    if (!cohortDataset || !cohortDataset.monthly_trends) return;

    const trends = cohortDataset.monthly_trends;
    
    // Filters: remove tailing incomplete records (Olist finishes at 2018-09, which is a partial month)
    const filteredTrends = trends.filter(t => t.order_month >= '2017-01' && t.order_month <= '2018-08');

    const labels = filteredTrends.map(t => t.order_month);
    const revenueData = filteredTrends.map(t => t.monthly_revenue);
    const customerData = filteredTrends.map(t => t.active_customers);

    if (trendsChartInstance) trendsChartInstance.destroy();

    trendsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Monthly Revenue ($)',
                    type: 'bar',
                    data: revenueData,
                    backgroundColor: 'rgba(59, 130, 246, 0.4)',
                    borderColor: '#3b82f6',
                    borderWidth: 1.5,
                    yAxisID: 'y'
                },
                {
                    label: 'Active Customers',
                    type: 'line',
                    data: customerData,
                    borderColor: '#a855f7',
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    pointRadius: 3,
                    yAxisID: 'y1',
                    tension: 0.2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#f3f4f6', font: { family: 'Outfit', weight: 600 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af', font: { family: 'Outfit' } }
                },
                y: {
                    position: 'left',
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { 
                        color: '#9ca3af', 
                        font: { family: 'Outfit' },
                        callback: function(value) { return '$' + (value / 1000).toFixed(0) + 'k'; }
                    }
                },
                y1: {
                    position: 'right',
                    grid: { drawOnChartArea: false }, // Only show left grid
                    ticks: { 
                        color: '#9ca3af',
                        font: { family: 'Outfit' },
                        callback: function(value) { return formatNumber(value); }
                    }
                }
            }
        }
    });
}

// Populate Top Categories Data Table
function populateCategoryTable(categories) {
    const tbody = document.querySelector('#category-table tbody');
    let html = '';
    
    categories.forEach(item => {
        // Capitalize category name nicely
        const name = item.category ? item.category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Unknown';
        
        html += `
            <tr>
                <td><strong>${name}</strong></td>
                <td>${formatNumber(item.repeat_customers)}</td>
                <td>${formatNumber(item.total_orders)}</td>
                <td>${formatCurrency(item.total_sales)}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// Populate Geographic Distribution Data Table
function populateGeoTable(geo) {
    const tbody = document.querySelector('#geo-table tbody');
    let html = '';
    
    geo.forEach(item => {
        html += `
            <tr>
                <td><strong>${item.state}</strong></td>
                <td>${formatNumber(item.total_customers)}</td>
                <td>${formatCurrency(item.state_revenue)}</td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// Tab Switching logic for SQL Code Viewer
function switchSqlTab(evt, tabId) {
    // Hide all blocks
    const codeBlocks = document.querySelectorAll('.sql-code-block');
    codeBlocks.forEach(block => block.classList.remove('active'));

    // Remove active status from all tab buttons
    const tabs = document.querySelectorAll('.sql-tab');
    tabs.forEach(tab => tab.classList.remove('active'));

    // Show current tab and highlight button
    document.getElementById(tabId).classList.add('active');
    evt.currentTarget.classList.add('active');
}
