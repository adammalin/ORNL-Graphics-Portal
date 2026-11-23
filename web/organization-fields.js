import {searchSelect,uniqueChoices} from './search-select.js';

export function organizationInputs(options={},groups=[],values={},prefix='',canRoute=true){
  return `${canRoute?`${searchSelect(prefix+'directorate','Directorate',{options:options.directorate||[],value:values.directorate||''})}${searchSelect(prefix+'division','Division / office / facility',{options:options.division||[],value:values.division||''})}`:''}${searchSelect(prefix+'requestorGroup','Group / department',{options:uniqueChoices(groups),value:values.requestorGroup||'',allowCustom:true,full:true})}`;
}
