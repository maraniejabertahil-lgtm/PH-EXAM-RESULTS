import { getFirebaseConfig } from "../../lib/firebase.js";
export async function onRequestGet(context) { return getFirebaseConfig(context); }
