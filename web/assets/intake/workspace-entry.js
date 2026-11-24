// Classic comparison uses the original client form, separate from the staff app.
if(window.PORTAL_CONFIG?.intakeComparison && window.PORTAL_CONFIG.intakeVersion==='classic'){
  await import('./classic-demo.js');
}else{
  await import('../../app.js');
}
