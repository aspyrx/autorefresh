# autorefresh

Serve a file. Trigger browser refresh on SIGHUP.

This uses the [EventSource browser APIs][EventSource] to interact with
[server-sent events][SSE].

This script is intended for usage with `latexmk -pvc`, e.g.:
```
$pdf_previewer = "./autorefresh.py";
$pdf_update_method = 2;     # via signal
$pdf_update_signal = 1;     # SIGHUP
```

[EventSource]: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
[SSE]: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events

