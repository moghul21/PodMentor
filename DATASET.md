# Dataset

| File | Source URL | Pages / Files | Licence / terms | Downloaded on |
|---|---|---|---|---|
| `data/raw/kubernetes` (HTML index) | [github.com/kubernetes/kubernetes](https://github.com/kubernetes/kubernetes) | 17,000+ Go source files in repo | Apache License 2.0 | 2026-10-24 |
| `data/sample/node_lifecycle_controller.go` | [kubernetes/pkg/controller/nodelifecycle](https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/nodelifecycle/node_lifecycle_controller.go) | ~1,600 lines | Apache License 2.0 | 2026-10-25 |
| `data/sample/scheduler.go` | [kubernetes/pkg/scheduler/scheduler.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/scheduler.go) | ~600 lines | Apache License 2.0 | 2026-10-25 |
| `data/sample/kubelet.go` (header) | [kubernetes/pkg/kubelet/kubelet.go](https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/kubelet.go) | ~3,000 lines | Apache License 2.0 | 2026-10-25 |

Full data lives in `data/raw/` (not committed — excluded via `.gitignore`). A 3-file sample is in `data/sample/`.

## Notes

- The Kubernetes repository is licensed under the **Apache License 2.0**, which allows redistribution of source files with attribution.
- The sample files in `data/sample/` are representative Go source files from the components most relevant to PodMentor's question set (scheduler, kubelet, node lifecycle controller).
- The `data/raw/kubernetes` file downloaded on 2026-10-24 is the GitHub repository index page (HTML) — it was used to verify access and count. Actual Go source files are obtained from the public repository.

