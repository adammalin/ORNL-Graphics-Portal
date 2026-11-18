/* One read in flight; a save invalidates older responses before they can repaint. */
export function createWorkspaceSync({read,canApply,apply,status=()=>{},failed=()=>{},now=()=>Date.now()}){
  let pending=null,epoch=0,lastAttempt=-Infinity;
  return {
    invalidate(){epoch++;},
    async check({force=false}={}){
      if(pending||!canApply()||(!force&&now()-lastAttempt<5000))return;
      const started=epoch;lastAttempt=now();status('checking');
      pending=(async()=>{
        try{const data=await read(force);if(started!==epoch)return;if(!canApply()){status('paused');return;}if(!data.unchanged)apply(data);status('synced');}
        catch(error){if(started===epoch){status('error',error);failed(error);}}
      })();
      try{await pending;}finally{pending=null;}
    }
  };
}
