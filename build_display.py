"""Build a classic-script display bundle; avoids OS-specific module MIME mappings."""
from pathlib import Path
import re
root=Path(__file__).parent/'web/spectator'
model=(root/'model.mjs').read_text()
viewer=(root/'viewer.js').read_text()
viewer=re.sub(r'^import\s*\{.*?\}\s*from\s*"./model.mjs";\s*','',viewer,count=1,flags=re.S)
viewer=viewer.replace('const base = new URL(".", import.meta.url);', 'const base = new URL(".", document.currentScript.src);')
viewer=viewer.replace('(document.querySelector(".container") || document.body).append(root);','(document.getElementById("visual-relay") || document.querySelector(".container") || document.body).append(root);')
viewer=viewer.replace('new URL("viewer.css", base)','new URL("viewer.css?v=rowan-2", base)')
viewer=viewer.replace('function render() {', 'function render() {\n  if (document.getElementById(\"visual-relay\")) return;')
# Source pages and the classic entry use the same renderer, without exporting an input interface.
model=re.sub(r'\bexport\s+','',model);viewer=re.sub(r'\bexport\s+','',viewer)
boot='''
const loadStatus = document.getElementById('visual-load-status');
const openButton = document.getElementById('show-visual');
if (openButton) {
  ready.then(() => {
    loadStatus.textContent = 'Ready. Open the linked visual window.';
    openButton.disabled = false;
    openButton.onclick = () => {
      const child = window.open(new URL('standalone.html?session='+encodeURIComponent(session),base),
        'dotdew-visual-'+session, 'width=1150,height=850');
      loadStatus.textContent = child ? 'Visual window connected. Keep this game page open.' : 'Allow pop-ups for this site, then press Open visual display again.';
    };
  }).catch(error => {loadStatus.textContent='Visual assets failed: '+error.message;});
}
'''

error='''
} catch(error) {
 const status=document.getElementById('visual-load-status');
 if(status) status.textContent='Visual display error: '+error.message;
 const hint=document.getElementById('visual-placeholder');
 if(hint) hint.textContent='The visual display could not start. Reload this page. '+error.message;
 console.error('Visual display failed',error);
}
})();
'''
(root/'display.js').write_text('(function(){\n"use strict";\ntry {\n'+model+'\n'+viewer+'\n'+boot+error)
