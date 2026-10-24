// Viewer-request on the S3 (default) behavior only. Any path whose last
// segment has no file extension is an SPA route, so serve index.html and let
// the client router take it. Attached per-behavior rather than as a
// distribution-wide custom error response, which would also turn API 404s
// into index.html.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);

  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
