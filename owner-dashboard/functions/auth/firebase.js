import { establishFirebaseProof, firebasePreflight } from "../lib/firebase.js";
export async function onRequestPost(context) { return establishFirebaseProof(context); }
export async function onRequestOptions(context) { return firebasePreflight(context); }
