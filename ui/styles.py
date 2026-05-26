"""Streamlit 페이지의 인라인 CSS.

main.py에 박혀있던 ~95줄의 <style>...</style>을 분리.
"""

PAGE_CSS = """
<style>
    .main > div { padding-top: 0.5rem; max-width: 1200px; margin: 0 auto; }
    .main-header { text-align: center; padding: 1rem 0 0.5rem 0; border-bottom: 1px solid #f1f5f9; margin-bottom: 1rem; }
    .main-title { font-size: 2rem; font-weight: 700; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .main-subtitle { font-size: 1rem; color: #64748b; margin: 0.3rem 0 0 0; }
    .input-section { background: white; padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0;
                     margin-bottom: 1rem; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
    .input-header { font-size: 1.1rem; font-weight: 600; color: #334155; margin: 0 0 1rem 0; }
    .popular-stocks { background: #f8fafc; padding: 0.8rem; border-radius: 6px; border: 1px solid #e2e8f0; }
    .popular-title { font-size: 0.85rem; font-weight: 600; color: #475569; margin: 0 0 0.5rem 0; text-align: center; }
    .stock-btn { display: block; width: 100%; padding: 0.4rem; margin: 0.2rem 0; background: white;
                 border: 1px solid #e2e8f0; border-radius: 4px; color: #334155; font-size: 0.75rem;
                 text-align: center; transition: all 0.15s ease; cursor: pointer; }
    .stock-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }
    .progress-section { background: white; padding: 1rem; border-radius: 8px; border: 1px solid #e2e8f0;
                        margin: 0.8rem 0; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
    .progress-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem; }
    .progress-title { font-size: 1rem; font-weight: 600; color: #334155; margin: 0; }
    .progress-percentage { font-size: 1rem; font-weight: 600; color: #667eea; }
    .progress-bar { width: 100%; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; margin: 0.3rem 0; }
    .progress-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 3px; transition: width 0.3s ease; }
    .progress-status { font-size: 0.85rem; color: #64748b; margin: 0.3rem 0 0 0; }
    .results-section { margin-top: 1rem; }
    .result-card { background: white; border-radius: 8px; padding: 1rem; margin: 0.8rem 0; border: 1px solid #e2e8f0;
                   box-shadow: 0 1px 4px rgba(0,0,0,0.04); border-left: 3px solid var(--accent-color); }
    .result-header { display: flex; align-items: center; margin-bottom: 0.8rem; padding-bottom: 0.8rem; border-bottom: 1px solid #f1f5f9; }
    .result-icon { font-size: 1.2rem; margin-right: 0.8rem; width: 32px; height: 32px; border-radius: 6px;
                   display: flex; align-items: center; justify-content: center; background: var(--bg-color); }
    .result-title { flex: 1; }
    .result-name { font-size: 1rem; font-weight: 600; color: var(--accent-color); margin: 0; }
    .result-desc { font-size: 0.8rem; color: #64748b; margin: 0.2rem 0 0 0; }
    .result-status { padding: 0.25rem 0.6rem; border-radius: 8px; font-size: 0.7rem; font-weight: 500; text-transform: uppercase; }
    .status-waiting { background: #f1f5f9; color: #64748b; }
    .status-running { background: #fef3c7; color: #92400e; animation: pulse 2s infinite; }
    .status-completed { background: #dcfce7; color: #166534; }
    .result-content { line-height: 1.5; color: #374151; font-size: 0.9rem; white-space: pre-wrap; }
    .final-report { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
                    padding: 1.5rem; border-radius: 8px; margin: 1.5rem 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .report-title { font-size: 1.3rem; font-weight: 700; margin: 0 0 0.8rem 0; }
    .report-content { background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 6px;
                      backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); line-height: 1.5;
                      white-space: pre-wrap; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    @media (max-width: 768px) { .main-title { font-size: 1.8rem; } .input-section { padding: 0.8rem; } }

    /* 투자 의견 카드 스타일 (Level 3) */
    .investment-opinion-card { background: white; border-radius: 12px; padding: 1.5rem; margin: 1.5rem 0;
                               border: 2px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
    .opinion-header { text-align: center; padding: 1.5rem; background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
                      border-radius: 8px; margin-bottom: 1.5rem; }
    .opinion-title { font-size: 1.3rem; font-weight: 700; color: #334155; margin: 0 0 1rem 0; }
    .opinion-main { font-size: 2rem; font-weight: 800; margin: 0.5rem 0; display: flex; align-items: center;
                    justify-content: center; gap: 0.8rem; }
    .opinion-buy { color: #16a34a; }
    .opinion-hold { color: #ea580c; }
    .opinion-sell { color: #dc2626; }
    .confidence-section { margin: 1rem 0; }
    .confidence-label { font-size: 0.9rem; color: #64748b; margin-bottom: 0.5rem; display: flex;
                        justify-content: space-between; align-items: center; }
    .confidence-bar { width: 100%; height: 24px; background: #f1f5f9; border-radius: 12px; overflow: hidden; }
    .confidence-fill { height: 100%; border-radius: 12px; transition: width 0.5s ease; display: flex;
                       align-items: center; justify-content: center; color: white; font-weight: 600; font-size: 0.85rem; }
    .confidence-high { background: linear-gradient(90deg, #16a34a, #22c55e); }
    .confidence-medium { background: linear-gradient(90deg, #2563eb, #3b82f6); }
    .confidence-low { background: linear-gradient(90deg, #ea580c, #f97316); }
    .confidence-very-low { background: linear-gradient(90deg, #dc2626, #ef4444); }
    .timeframe-badge { display: inline-block; padding: 0.4rem 1rem; background: #ede9fe; color: #7c3aed;
                       border-radius: 20px; font-size: 0.85rem; font-weight: 600; margin-top: 0.5rem; }
    .opinion-section { margin: 1.5rem 0; padding: 1rem; background: #fafafa; border-radius: 8px; }
    .section-title { font-size: 1rem; font-weight: 600; color: #334155; margin: 0 0 0.8rem 0; display: flex;
                     align-items: center; gap: 0.5rem; }
    .reasoning-text { line-height: 1.6; color: #475569; font-size: 0.95rem; white-space: pre-wrap; }
    .factor-list { list-style: none; padding: 0; margin: 0.5rem 0 0 0; }
    .factor-item { padding: 0.6rem; margin: 0.4rem 0; background: white; border-radius: 6px;
                   border-left: 3px solid; display: flex; align-items: flex-start; gap: 0.6rem; }
    .factor-positive { border-left-color: #16a34a; }
    .factor-risk { border-left-color: #dc2626; }
    .factor-icon { font-size: 1.1rem; margin-top: 0.1rem; }
    .factor-text { flex: 1; color: #475569; font-size: 0.9rem; line-height: 1.4; }

    /* Level 3: 목표가, 손절가, R/R, 분할매수 */
    .price-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }
    .price-item { background: #f9fafb; padding: 1rem; border-radius: 8px; border: 1px solid #e5e7eb; }
    .price-label { font-size: 0.8rem; color: #6b7280; margin-bottom: 0.3rem; font-weight: 600; }
    .price-value { font-size: 1.3rem; font-weight: 700; color: #111827; }
    .price-value.target { color: #16a34a; }
    .price-value.stop { color: #dc2626; }
    .price-value.ratio { color: #2563eb; }
    .split-buy-table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
    .split-buy-table th { background: #f3f4f6; padding: 0.6rem; text-align: left; font-size: 0.85rem; color: #374151; font-weight: 600; border-bottom: 2px solid #e5e7eb; }
    .split-buy-table td { padding: 0.6rem; font-size: 0.85rem; color: #4b5563; border-bottom: 1px solid #f3f4f6; }
    .split-buy-table tr:hover { background: #f9fafb; }
</style>
"""
