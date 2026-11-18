/* Never parse an HTML gateway/sign-in page as a successful portal response. */
export async function readPortalJson(response){
  if(!response.headers.get('content-type')?.toLowerCase().includes('application/json')){
    const error=new Error('Sign-in or network access needs attention. Reopen the portal. This operation is not confirmed; inspect the job before retrying a save.');
    error.status=[401,403].includes(response.status)?response.status:502;throw error;
  }
  let data;
  try{data=await response.json();}catch{
    const error=new Error('The portal returned an unreadable response. The operation is not confirmed; inspect the job before retrying.');error.status=502;throw error;
  }
  if(!response.ok){const error=new Error(typeof data?.error==='string'?data.error:'The portal operation could not be confirmed.');error.status=response.status;throw error;}
  return data;
}
export const mediaType = value => String(value||'').split(';',1)[0].trim().toLowerCase();
