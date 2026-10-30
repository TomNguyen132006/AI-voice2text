// A private copy of a course on THIS machine only: frontend/public/local-only/ is git-ignored, so its files never reach the repo
// or the deployed site. The files are asked for only on a local address; on any other host nothing is requested.
export const LOCAL_DIR = '/local-only/'
export const isLocalHost = () => ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
