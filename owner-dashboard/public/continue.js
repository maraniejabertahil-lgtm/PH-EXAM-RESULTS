const message=document.querySelector("#handoff-message");
const returnLink=document.querySelector("#return-link");
function fail(text){message.textContent=text;returnLink.hidden=false;}
const proof=new URLSearchParams(location.hash.slice(1)).get("proof");
history.replaceState(null,"",location.pathname);
if(!proof||proof.length>5000){
  fail("The secure sign-in handoff is missing or expired. Return to the public page and sign in again.");
}else{
  try{
    const response=await fetch("/auth/firebase/complete",{
      method:"POST",
      credentials:"same-origin",
      headers:{"Content-Type":"application/json",Accept:"application/json"},
      body:JSON.stringify({proof}),
      cache:"no-store",
    });
    const result=await response.json().catch(()=>null);
    if(!response.ok||result?.authenticated!==true)throw new Error(result?.error||"Firebase proof could not be completed.");
    location.replace("/");
  }catch(error){
    fail(error instanceof Error?error.message:"Secure sign-in could not be completed. Return to the public page and try again.");
  }
}
