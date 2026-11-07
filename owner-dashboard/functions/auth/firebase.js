import { establishFirebaseProof } from "../lib/firebase.js";
export async function onRequestPost(context) { return establishFirebaseProof(context); }
