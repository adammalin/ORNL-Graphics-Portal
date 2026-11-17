export const STAGES = ['New', 'Assigned', 'Accepted', 'In Progress', 'In Review', 'Completed', 'Archived'];
export const CLOSED = new Set(['Completed', 'Archived']);
export const DESIGNERS = [
  { id: 'alex', name: 'Alex Rivera', initials: 'AR', capacity: 28 },
  { id: 'morgan', name: 'Morgan Lee', initials: 'ML', capacity: 28 },
  { id: 'sam', name: 'Sam Chen', initials: 'SC', capacity: 24 },
];
export const TASK_TYPES = ['Figure / Diagram / Chart', 'Presentation', 'Poster', 'Fact sheet / Flyer / Handout', 'Publication / Report', 'Web / Digital graphic', 'Other / Not sure'];
export function assignedDesigner(project) { return project.response === 'accepted' ? (project.requestedDesigner || '') : ''; }
export function isActive(project) { return !CLOSED.has(project.stage); }
export function myProjects(projects, person) { return projects.filter(p => isActive(p) && assignedDesigner(p) === person); }
export function daysUntil(date, now = new Date()) {
  if (!date) return null;
  const d = new Date(`${date.slice(0,10)}T12:00:00`);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  return Number.isNaN(+d) ? null : Math.round((d - today) / 86400000);
}
export function metrics(projects, now = new Date()) {
  const active = projects.filter(isActive);
  return { active: active.length, newRequests: active.filter(p => p.stage === 'New').length,
    dueSoon: active.filter(p => { const days = daysUntil(p.dueDate, now); return days !== null && days >= 0 && days <= 7; }).length,
    overdue: active.filter(p => { const days = daysUntil(p.dueDate, now); return days !== null && days < 0; }).length,
    hours: active.reduce((n,p) => n + (Number(p.hours) || 0), 0), closed: projects.length - active.length };
}
export function workload(projects, designers = DESIGNERS) {
  return designers.map(person => { const jobs = myProjects(projects, person.id); return { ...person, jobs: jobs.length,
    hours: jobs.reduce((sum,p) => sum + (Number(p.hours) || 0), 0),
    offers: projects.filter(p => isActive(p) && p.requestedDesigner === person.id && p.response !== 'accepted' && p.response !== 'declined').length }; });
}
export function moveProject(project, stage, now = new Date()) {
  if (!STAGES.includes(stage)) throw new Error('Choose a valid project stage.');
  if (stage === 'Assigned' && !project.requestedDesigner) throw new Error('Offer this job to a designer before moving it to Assigned.');
  if (['Accepted', 'In Progress', 'In Review', 'Completed'].includes(stage) && !assignedDesigner(project)) throw new Error('Record a designer’s acceptance before starting this job.');
  return { ...project, stage, completedDate: CLOSED.has(stage) ? (project.completedDate || now.toISOString().slice(0,10)) : project.completedDate };
}
export function safeUrl(value) { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; } catch { return null; } }
export function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
export function filterProjects(projects, { query = '', designer = '', stage = '' } = {}) {
  const q = query.trim().toLowerCase();
  return projects.filter(p => (!q || [p.id,p.title,p.description,p.requestor,p.taskType].some(v => String(v || '').toLowerCase().includes(q))) && (!designer || assignedDesigner(p) === designer || p.requestedDesigner === designer) && (!stage || p.stage === stage));
}
export function validateRequest(values) {
  const errors = {};
  for (const [key,label] of [['title','Project title'],['description','Project details'],['requestor','Your name'],['email','Your email'],['taskType','Type of work']]) if (!String(values[key] || '').trim()) errors[key] = `${label} is required.`;
  if (values.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email)) errors.email = 'Enter a valid email address.';
  for (const key of ['reference1','reference2']) if (values[key] && !safeUrl(values[key])) errors[key] = 'Enter a complete http:// or https:// link.';
  return errors;
}
