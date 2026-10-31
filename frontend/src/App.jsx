import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, Camera, CheckCircle2, Clock3, MapPin, Plus, ShieldCheck, Sparkles, Upload, X } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const demo = [
  {id:'DEMO-104',issue_type:'Pothole',severity:'High',title:'Damaged road surface near market',location:'Sample location',status:'Under Review',department:'Road Maintenance',created_at:new Date().toISOString()},
  {id:'DEMO-103',issue_type:'Garbage',severity:'Medium',title:'Uncollected waste near public bin',location:'Sample location',status:'Submitted',department:'Sanitation',created_at:new Date().toISOString()},
  {id:'DEMO-102',issue_type:'Broken streetlight',severity:'Low',title:'Streetlight appears non-functional',location:'Sample location',status:'Resolved',department:'Electrical Maintenance',created_at:new Date().toISOString()}
];

export default function App(){
  const [reports,setReports]=useState(demo), [show,setShow]=useState(false), [file,setFile]=useState(null);
  const [preview,setPreview]=useState(''), [description,setDescription]=useState(''), [location,setLocation]=useState('');
  const [provider,setProvider]=useState('gemini'), [analysis,setAnalysis]=useState(null), [busy,setBusy]=useState(false);
  const [error,setError]=useState(''), [notice,setNotice]=useState('');
  async function refresh(){try{const r=await fetch(`${API}/api/reports`);if(r.ok){const d=await r.json();setReports(d.length?d:demo)}}catch{}}
  useEffect(()=>{refresh()},[]);
  function choose(f){if(!f)return;setFile(f);setPreview(URL.createObjectURL(f));setAnalysis(null);setError('')}
  async function analyze(e){e.preventDefault();if(!file){setError('Please choose an image first.');return}
    setBusy(true);setError('');setAnalysis(null);
    try{const fd=new FormData();fd.append('image',file);fd.append('description',description);fd.append('location',location);fd.append('provider',provider);
      const r=await fetch(`${API}/api/analyze`,{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Analysis failed');setAnalysis(d);
    }catch(err){setError(err.message)}finally{setBusy(false)}}
  async function submitReport(){if(!analysis)return;setBusy(true);setError('');
    try{const r=await fetch(`${API}/api/reports`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({analysis,location,description,image_name:file?.name||''})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||'Could not save report');setNotice(`Report ${d.id} submitted successfully.`);setAnalysis(null);setFile(null);setPreview('');setDescription('');setLocation('');setShow(false);await refresh();
    }catch(err){setError(err.message)}finally{setBusy(false)}}
  const high=reports.filter(x=>x.severity==='High').length;
  const resolved=reports.filter(x=>x.status==='Resolved').length;
  return <div className="app">
    <header className="top"><a className="brand" href="#"><span className="brandmark">C</span><span>Civic<span className="green">Pulse</span><small>COMMUNITY ISSUE INTELLIGENCE</small></span></a><nav><a href="#reports">Explore reports</a><button className="primary small" onClick={()=>{setShow(true);setNotice('')}}><Plus size={16}/> Report an issue</button></nav></header>
    <main>
      <section className="hero"><div className="hero-copy"><div className="eyebrow"><span className="dot"/> YOUR CITY. YOUR VOICE.</div><h1>Small reports.<br/><em>Meaningful change.</em></h1><p>Turn the civic issues you see every day into clear, actionable reports. AI helps document the problem. Your community helps bring it to light.</p><div className="hero-actions"><button className="primary" onClick={()=>setShow(true)}><Camera size={17}/> Report an issue <ArrowUpRight size={16}/></button><a className="textlink" href="#reports">View community reports ↓</a></div><div className="trust"><ShieldCheck size={16}/> AI-assisted · Human-reviewed · Community-powered</div></div>
      <div className="hero-art"><div className="art-label"><Activity size={16}/> COMMUNITY PULSE <b>LIVE BOARD</b></div><div className="road"><div className="roadline"/><div className="pothole p1"/><div className="pothole p2"/></div><div className="floatcard"><span className="badge high">HIGH PRIORITY</span><b>Road damage reported</b><small><MapPin size={12}/> Community report · Awaiting review</small></div></div></section>
      <section className="stats"><div><span className="stat-icon"><Activity/></span><div><b>{reports.length}</b><small>Community reports</small></div></div><div><span className="stat-icon amber"><AlertTriangle/></span><div><b>{high}</b><small>High priority</small></div></div><div><span className="stat-icon mint"><CheckCircle2/></span><div><b>{resolved}</b><small>Marked resolved</small></div></div><div className="stat-note">Every report starts with someone<br/>who cares enough to speak up.</div></section>
      <section id="reports" className="reports"><div className="section-head"><div><div className="eyebrow">THE COMMUNITY BOARD</div><h2>Issues worth <em>seeing.</em></h2><p>A shared view of what needs attention in our neighbourhoods.</p></div><button className="outline" onClick={()=>setShow(true)}><Plus size={16}/> Add a report</button></div>
      <div className="cards">{reports.map((r,i)=><article className="report" key={r.id}><div className="report-top"><span className="type">{r.issue_type}</span><span className={`badge ${(r.severity||'').toLowerCase()}`}>{r.severity} priority</span></div><h3>{r.title}</h3><p className="loc"><MapPin size={13}/>{r.location||'Location not specified'}</p><div className="report-foot"><span><span className={`status ${(r.status||'').replaceAll(' ','-').toLowerCase()}`}/>{r.status}</span><small>#{r.id}</small></div></article>)}</div>
      </section>
      <section className="how"><div><div className="eyebrow">HOW CIVICPULSE WORKS</div><h2>From a photo to a <em>clearer picture.</em></h2></div><div className="steps"><div><span>01</span><b>Capture</b><p>Share a photo and tell us what you noticed.</p></div><div><span>02</span><b>Understand</b><p>Gemma 4 helps identify visible details and organise the report.</p></div><div><span>03</span><b>Verify & share</b><p>Review the findings before adding them to the community board.</p></div></div></section>
    </main>
    <footer><div className="brand"><span className="brandmark">C</span><span>Civic<span className="green">Pulse</span><small>SEE IT. REPORT IT. IMPROVE IT.</small></span></div><span>Built for communities, powered by open-weight AI.</span></footer>
    {show&&<div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShow(false)}}><div className="modal"><div className="modal-head"><div><div className="eyebrow">COMMUNITY REPORT</div><h2>Make it <em>visible.</em></h2></div><button className="iconbtn" onClick={()=>setShow(false)}><X/></button></div>
      <form onSubmit={analyze}><label className="upload">{preview?<img src={preview}/>:<><Upload size={25}/><b>Drop an issue photo here</b><small>JPG, PNG or WEBP · Max 8 MB</small></>}<input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>choose(e.target.files?.[0])}/></label>
      <label>What did you notice? <textarea value={description} onChange={e=>setDescription(e.target.value)} placeholder="Describe the issue (optional)"/></label>
      <label>Where is it? <input value={location} onChange={e=>setLocation(e.target.value)} placeholder="Street, area or landmark"/></label>
      <label>AI provider <select value={provider} onChange={e=>setProvider(e.target.value)}><option value="gemini">Gemma 4 · Gemini API</option><option value="local">Gemma 4 · Local Ollama</option></select></label>
      <button className="primary full" disabled={busy}>{busy?'Analysing image…':<><Sparkles size={16}/> Analyse with Gemma 4</>}</button></form>
      {error&&<div className="error">{error}</div>}
      {analysis&&<div className="analysis"><div className="analysis-title"><Sparkles size={17}/> AI findings <span className="badge">{analysis.provider}</span></div><div className="analysis-grid"><div><small>ISSUE</small><b>{analysis.issue_type}</b></div><div><small>PRELIMINARY SEVERITY</small><b>{analysis.severity}</b></div><div><small>SUGGESTED DEPARTMENT</small><b>{analysis.department}</b></div></div><h3>{analysis.title}</h3><p>{analysis.description}</p><b className="subhead">Visible evidence</b><ul>{analysis.evidence?.map((x,i)=><li key={i}>{x}</li>)}</ul>{analysis.limitations?.length>0&&<p className="limitation">Limitations: {analysis.limitations.join('; ')}</p>}<p className="disclaimer">AI-generated preliminary assessment. Please verify details before submitting.</p><button className="primary full" onClick={submitReport} disabled={busy}><CheckCircle2 size={16}/> Confirm & publish report</button></div>}
    </div></div>}
    {notice&&<div className="toast"><CheckCircle2 size={17}/>{notice}<button onClick={()=>setNotice('')}><X size={15}/></button></div>}
  </div>
}
