import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Eye,
  FileText,
  MapPin,
  RefreshCw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import './dashboard.css';

const SEVERITIES = ['Low', 'Medium', 'High', 'Unclear'];
const STATUSES = ['Submitted', 'Under Review', 'Resolved'];

function text(value, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function reportDate(value) {
  if (typeof value !== 'string') return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value, options = { dateStyle: 'medium' }) {
  const date = reportDate(value);
  return date ? new Intl.DateTimeFormat(undefined, options).format(date) : 'Date unavailable';
}

function reportSeverity(report) {
  const severity = text(report.severity);
  return SEVERITIES.includes(severity) ? severity : 'Unclear';
}

function groupBy(reports, field, fallback) {
  const counts = new Map();
  reports.forEach((report) => {
    const value = text(report[field], fallback);
    counts.set(value, (counts.get(value) || 0) + 1);
  });
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function trendData(reports) {
  const dated = reports
    .map((report) => reportDate(report.created_at))
    .filter(Boolean)
    .sort((a, b) => a.getTime() - b.getTime());

  if (dated.length < 2) return { interval: '', items: [] };

  const span = dated[dated.length - 1].getTime() - dated[0].getTime();
  const monthly = span > 45 * 24 * 60 * 60 * 1000;
  const counts = new Map();

  reports.forEach((report) => {
    const date = reportDate(report.created_at);
    if (!date) return;
    const key = monthly
      ? `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`
      : date.toISOString().slice(0, 10);
    counts.set(key, (counts.get(key) || 0) + 1);
  });

  const keys = [...counts.keys()].sort();
  if (keys.length < 2) return { interval: '', items: [] };

  const visibleKeys = keys.slice(-12);
  const maximum = Math.max(...visibleKeys.map((key) => counts.get(key)));
  const items = visibleKeys.map((key) => {
    const date = monthly
      ? new Date(`${key}-01T00:00:00Z`)
      : new Date(`${key}T00:00:00Z`);
    return {
      label: new Intl.DateTimeFormat(undefined, monthly
        ? { month: 'short', year: '2-digit', timeZone: 'UTC' }
        : { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(date),
      count: counts.get(key),
      height: `${Math.max(8, (counts.get(key) / maximum) * 100)}%`,
    };
  });
  return { interval: monthly ? 'Monthly' : 'Daily', items };
}

function Distribution({ title, icon: Icon, rows, emptyLabel = 'No reports to summarize yet.' }) {
  const maximum = Math.max(1, ...rows.map((row) => row.count));
  return (
    <section className="dashboard-panel">
      <div className="dashboard-panel-heading">
        <span className="dashboard-panel-icon"><Icon size={17} /></span>
        <h3>{title}</h3>
      </div>
      {rows.length ? (
        <div className="distribution-list">
          {rows.map(({ label, count }) => (
            <div className="distribution-row" key={label}>
              <div className="distribution-label">
                <span>{label}</span>
                <b>{count}</b>
              </div>
              <div className="distribution-track" aria-label={`${count} reports`}>
                <span style={{ width: `${(count / maximum) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : <p className="dashboard-chart-empty">{emptyLabel}</p>}
    </section>
  );
}

function ReportDetails({ report, onClose }) {
  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const evidence = Array.isArray(report.evidence)
    ? report.evidence.filter((item) => typeof item === 'string' && item.trim())
    : [];
  const limitations = Array.isArray(report.limitations)
    ? report.limitations.filter((item) => typeof item === 'string' && item.trim())
    : [];
  const confidence = report.confidence;

  return (
    <div className="dashboard-modal-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className="dashboard-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-details-title"
      >
        <div className="dashboard-modal-heading">
          <div>
            <span className="dashboard-kicker">COMMUNITY REPORT</span>
            <h2 id="report-details-title">{text(report.title, 'Untitled report')}</h2>
          </div>
          <button className="dashboard-icon-button" type="button" onClick={onClose} aria-label="Close report details">
            <X size={19} />
          </button>
        </div>
        <div className="dashboard-detail-tags">
          <span>{text(report.issue_type, 'Uncategorized')}</span>
          <span className={`dashboard-severity ${reportSeverity(report).toLowerCase()}`}>
            {reportSeverity(report)} preliminary severity
          </span>
          <span className="dashboard-status">{text(report.status, 'Status unavailable')}</span>
        </div>
        <dl className="dashboard-detail-grid">
          <div><dt>Location</dt><dd>{text(report.location, 'Location not provided')}</dd></div>
          <div><dt>Suggested department</dt><dd>{text(report.department, 'Not specified')}</dd></div>
          <div><dt>Submitted</dt><dd>{formatDate(report.created_at, { dateStyle: 'medium', timeStyle: 'short' })}</dd></div>
          <div><dt>AI confidence</dt><dd>{Number.isFinite(confidence) && confidence >= 0 && confidence <= 1
            ? `${Math.round(confidence * 100)}% (not a calibrated probability)`
            : 'Not available'}</dd></div>
        </dl>
        <div className="dashboard-detail-section">
          <h3>Description</h3>
          <p>{text(report.description, 'No description was included.')}</p>
        </div>
        <div className="dashboard-detail-section">
          <h3>Image</h3>
          <p>{text(report.image_name)
            ? `Uploaded filename: ${text(report.image_name)}. The API does not provide a retrievable image.`
            : 'No image filename is available, and the API does not provide a retrievable image.'}</p>
        </div>
        <div className="dashboard-detail-section">
          <h3>AI-observed evidence</h3>
          {evidence.length
            ? <ul>{evidence.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            : <p>No evidence details were included.</p>}
        </div>
        <div className="dashboard-detail-section">
          <h3>Assessment limitations</h3>
          {limitations.length
            ? <ul>{limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            : <p>No limitations were included.</p>}
        </div>
        <p className="dashboard-disclaimer">
          This is a community-submitted report. AI classifications and severity are preliminary,
          not official inspections or verified municipal complaints.
        </p>
      </section>
    </div>
  );
}

export default function Dashboard({ api, onReport, refreshToken = 0 }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState(null);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [department, setDepartment] = useState('');
  const [location, setLocation] = useState('');
  const [selectedReport, setSelectedReport] = useState(null);

  const loadReports = useCallback(async (signal) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${api}/api/reports`, { signal });
      if (!response.ok) {
        throw new Error(`Reports could not be loaded (HTTP ${response.status}).`);
      }
      const data = await response.json();
      if (!Array.isArray(data) || data.some((report) => (
        !report || typeof report !== 'object' || Array.isArray(report)
      ))) {
        throw new Error('The reports API returned data in an unexpected format.');
      }
      setReports(data);
      setUpdatedAt(new Date());
    } catch (requestError) {
      if (requestError.name !== 'AbortError') {
        setError(requestError.message || 'Reports could not be loaded. Please try again.');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    const controller = new AbortController();
    void loadReports(controller.signal);
    return () => controller.abort();
  }, [loadReports, refreshToken]);

  const categories = useMemo(() => groupBy(reports, 'issue_type', 'Uncategorized'), [reports]);
  const departments = useMemo(() => groupBy(reports, 'department', 'Not specified'), [reports]);
  const locations = useMemo(() => groupBy(reports, 'location', 'Location not provided'), [reports]);
  const statuses = useMemo(() => groupBy(reports, 'status', 'Status unavailable'), [reports]);
  const filteredReports = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return reports.filter((report) => {
      const matchesSearch = !query
        || [report.title, report.description].some((value) => (
          typeof value === 'string' && value.toLocaleLowerCase().includes(query)
        ));
      return matchesSearch
        && (!category || text(report.issue_type, 'Uncategorized') === category)
        && (!severity || reportSeverity(report) === severity)
        && (!status || text(report.status, 'Status unavailable') === status)
        && (!department || text(report.department, 'Not specified') === department)
        && (!location || text(report.location, 'Location not provided') === location);
    });
  }, [reports, search, category, severity, status, department, location]);

  const trend = useMemo(() => trendData(reports), [reports]);
  const highSeverity = reports.filter((report) => reportSeverity(report) === 'High').length;
  const submitted = reports.filter((report) => report.status === 'Submitted').length;
  const underReview = reports.filter((report) => report.status === 'Under Review').length;
  const resolved = reports.filter((report) => report.status === 'Resolved').length;
  const hasFilters = Boolean(search || category || severity || status || department || location);

  function clearFilters() {
    setSearch('');
    setCategory('');
    setSeverity('');
    setStatus('');
    setDepartment('');
    setLocation('');
  }

  return (
    <main className="dashboard">
      <section className="dashboard-heading">
        <div>
          <span className="dashboard-kicker"><span className="dashboard-live-dot" /> PUBLIC COMMUNITY DATA</span>
          <h1>CivicPulse <em>Dashboard</em></h1>
          <p>A current view of reports shared through CivicPulse—not an official city record.</p>
        </div>
        <div className="dashboard-heading-actions">
          <span className="dashboard-updated">
            <Clock3 size={14} />
            {updatedAt
              ? `Updated ${new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(updatedAt)}`
              : 'Not yet updated'}
          </span>
          <button className="dashboard-refresh" type="button" onClick={() => void loadReports()} disabled={loading}>
            <RefreshCw size={15} className={loading ? 'dashboard-spinning' : ''} />
            Refresh
          </button>
          <button className="primary small dashboard-report-button" type="button" onClick={onReport}>
            + Report an issue
          </button>
        </div>
      </section>

      <div className="dashboard-disclaimer dashboard-banner">
        <ShieldCheck size={18} />
        <p>
          Reports are community-submitted. AI issue classifications and severity assessments are
          preliminary—not verified inspections or municipal complaints.
        </p>
      </div>

      {error && (
        <div className="dashboard-error" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
          <button type="button" onClick={() => void loadReports()}>Try again</button>
        </div>
      )}

      {loading && reports.length === 0 && !error ? (
        <div className="dashboard-loading" role="status">Loading community reports…</div>
      ) : error && reports.length === 0 ? (
        <div className="dashboard-empty dashboard-load-error">
          <AlertTriangle size={24} />
          <h2>Dashboard data is unavailable</h2>
          <p>Check that the CivicPulse API is running, then try again.</p>
          <button className="dashboard-refresh" type="button" onClick={() => void loadReports()}>
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      ) : (
        <>
          <section className="dashboard-stat-grid" aria-label="Report summary">
            <article className="dashboard-stat-card">
              <span className="dashboard-stat-icon"><FileText size={19} /></span>
              <span className="dashboard-stat-value">{reports.length}</span>
              <span className="dashboard-stat-label">Total reports</span>
            </article>
            <article className="dashboard-stat-card">
              <span className="dashboard-stat-icon"><Activity size={19} /></span>
              <span className="dashboard-stat-value">{submitted}</span>
              <span className="dashboard-stat-label">Submitted</span>
            </article>
            <article className="dashboard-stat-card">
              <span className="dashboard-stat-icon review"><Clock3 size={19} /></span>
              <span className="dashboard-stat-value">{underReview}</span>
              <span className="dashboard-stat-label">Under review</span>
            </article>
            <article className="dashboard-stat-card">
              <span className="dashboard-stat-icon resolved"><CheckCircle2 size={19} /></span>
              <span className="dashboard-stat-value">{resolved}</span>
              <span className="dashboard-stat-label">Resolved</span>
            </article>
            <article className="dashboard-stat-card">
              <span className="dashboard-stat-icon high"><AlertTriangle size={19} /></span>
              <span className="dashboard-stat-value">{highSeverity}</span>
              <span className="dashboard-stat-label">High preliminary severity</span>
            </article>
          </section>

          {reports.length === 0 && (
            <div className="dashboard-empty">
              <FileText size={25} />
              <h2>No community reports yet</h2>
              <p>When reports are shared through CivicPulse, their real data will appear here.</p>
              <button className="primary small" type="button" onClick={onReport}>Create the first report</button>
            </div>
          )}

          <section className="dashboard-chart-grid" aria-label="Report analytics">
            <Distribution title="Issue categories" icon={Activity} rows={categories} />
            <Distribution
              title="Preliminary AI severity"
              icon={AlertTriangle}
              rows={SEVERITIES.map((label) => ({
                label,
                count: reports.filter((report) => reportSeverity(report) === label).length,
              }))}
            />
            <Distribution title="Suggested departments" icon={Building2} rows={departments} />
            <section className="dashboard-panel dashboard-trend-panel">
              <div className="dashboard-panel-heading">
                <span className="dashboard-panel-icon"><CalendarDays size={17} /></span>
                <div>
                  <h3>Reports over time</h3>
                  <p>{trend.interval ? `${trend.interval} report counts` : 'Report counts'}</p>
                </div>
              </div>
              {trend.items.length >= 2 ? (
                <div className="dashboard-trend-chart" role="img" aria-label="Report counts over time">
                  {trend.items.map((item) => (
                    <div className="dashboard-trend-column" key={item.label}>
                      <b>{item.count}</b>
                      <span className="dashboard-trend-bar" style={{ height: item.height }} />
                      <small>{item.label}</small>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="dashboard-chart-empty">
                  More than one reporting date is needed to show a useful trend.
                </p>
              )}
            </section>
          </section>

          <section className="dashboard-location-panel dashboard-panel">
            <div className="dashboard-panel-heading">
              <span className="dashboard-panel-icon"><MapPin size={17} /></span>
              <div>
                <h3>Location mentions</h3>
                <p>Text supplied with reports; no map pins or geocoding.</p>
              </div>
            </div>
            {locations.length ? (
              <div className="dashboard-location-list">
                {locations.slice(0, 8).map(({ label, count }) => (
                  <div key={label}><span>{label}</span><b>{count}</b></div>
                ))}
                {locations.length > 8 && <small>Showing 8 of {locations.length} reported locations.</small>}
              </div>
            ) : <p className="dashboard-chart-empty">No location details have been submitted.</p>}
          </section>

          <section className="dashboard-recent-section">
            <div className="dashboard-recent-heading">
              <div>
                <span className="dashboard-kicker">COMMUNITY REPORTS</span>
                <h2>Recent reports</h2>
                <p>Showing {filteredReports.length} of {reports.length} reports</p>
              </div>
            </div>
            <div className="dashboard-filters">
              <label className="dashboard-search">
                <Search size={16} />
                <input
                  type="search"
                  placeholder="Search title or description"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <label>
                <span>Category</span>
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">All categories</option>
                  {categories.map(({ label }) => <option key={label} value={label}>{label}</option>)}
                </select>
              </label>
              <label>
                <span>Severity</span>
                <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
                  <option value="">All severities</option>
                  {SEVERITIES.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
              <label>
                <span>Status</span>
                <select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="">All statuses</option>
                  {STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
                  {statuses
                    .filter(({ label }) => !STATUSES.includes(label))
                    .map(({ label }) => <option key={label} value={label}>{label}</option>)}
                </select>
              </label>
              <label>
                <span>Department</span>
                <select value={department} onChange={(event) => setDepartment(event.target.value)}>
                  <option value="">All departments</option>
                  {departments.map(({ label }) => <option key={label} value={label}>{label}</option>)}
                </select>
              </label>
              <label>
                <span>Location</span>
                <select value={location} onChange={(event) => setLocation(event.target.value)}>
                  <option value="">All locations</option>
                  {locations.map(({ label }) => <option key={label} value={label}>{label}</option>)}
                </select>
              </label>
              {hasFilters && (
                <button className="dashboard-clear-filters" type="button" onClick={clearFilters}>
                  Clear filters
                </button>
              )}
            </div>

            {filteredReports.length ? (
              <div className="dashboard-report-list">
                {filteredReports.map((report, index) => (
                  <article className="dashboard-report-row" key={text(report.id, `report-${index}`)}>
                    <div className="dashboard-report-main">
                      <span className="dashboard-report-category">{text(report.issue_type, 'Uncategorized')}</span>
                      <h3>{text(report.title, 'Untitled report')}</h3>
                      <p><MapPin size={13} /> {text(report.location, 'Location not provided')}</p>
                    </div>
                    <div className="dashboard-report-meta">
                      <span className={`dashboard-severity ${reportSeverity(report).toLowerCase()}`}>
                        {reportSeverity(report)}
                      </span>
                      <span className="dashboard-report-status">{text(report.status, 'Status unavailable')}</span>
                      <time dateTime={text(report.created_at)}>{formatDate(report.created_at)}</time>
                    </div>
                    <button
                      className="dashboard-view-report"
                      type="button"
                      onClick={() => setSelectedReport(report)}
                    >
                      <Eye size={15} /><span>Details</span>
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <div className="dashboard-empty dashboard-filter-empty">
                <Search size={22} />
                <h3>No matching reports</h3>
                <p>Try a different search or clear the selected filters.</p>
                {hasFilters && <button className="dashboard-clear-filters" type="button" onClick={clearFilters}>Clear filters</button>}
              </div>
            )}
          </section>
        </>
      )}
      {selectedReport && <ReportDetails report={selectedReport} onClose={() => setSelectedReport(null)} />}
    </main>
  );
}
