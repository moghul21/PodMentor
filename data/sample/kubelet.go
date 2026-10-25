/*
Copyright 2015 The Kubernetes Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

// Source: https://github.com/kubernetes/kubernetes/blob/master/pkg/kubelet/kubelet.go
// Obtained: 2026-10-25 -- Apache License 2.0
// Representative excerpt for the PodMentor dataset sample.

// Package kubelet is the node agent of Kubernetes. It is responsible for
// running a set of pods on a node and reporting the status of those pods to
// the API server.
package kubelet

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	clientset "k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"
	internalapi "k8s.io/cri-api/pkg/apis"

	kubecontainer "k8s.io/kubernetes/pkg/kubelet/container"
	"k8s.io/kubernetes/pkg/kubelet/kuberuntime"
	"k8s.io/kubernetes/pkg/kubelet/pod"
	"k8s.io/kubernetes/pkg/kubelet/prober"
	"k8s.io/kubernetes/pkg/kubelet/status"
)

// Kubelet is the main kubelet implementation. It is the node agent that
// runs on every worker node in the cluster and is responsible for managing
// the pods scheduled to that node.
type Kubelet struct {
	nodeName        types.NodeName
	kubeClient      clientset.Interface
	heartbeatClient clientset.Interface
	rootDirectory   string

	// podWorkers handle syncing Pods in response to events (create/update/delete).
	podWorkers PodWorkers

	// podManager is responsible for managing the desired set of pods on this node.
	podManager pod.Manager

	// statusManager maintains the API server view of pod status and reconciles it.
	statusManager status.Manager

	// probeManager handles liveness, readiness, and startup probes.
	probeManager prober.Manager

	// containerRuntime is the CRI implementation (e.g., containerd, CRI-O).
	// It communicates with the container runtime via gRPC using the CRI API.
	containerRuntime kubecontainer.Runtime

	// runtimeService is the low-level CRI gRPC client used to call
	// RunPodSandbox, CreateContainer, StartContainer, StopContainer, etc.
	runtimeService internalapi.RuntimeService

	// runtimeClassManager manages RuntimeClass objects from the API server.
	runtimeClassManager *runtimeclass.Manager

	// resyncInterval is the interval between periodic full reconciliations.
	resyncInterval time.Duration

	// Maximum number of pods that can run on this node.
	maxPods int

	// syncLoopMonitor is used to detect liveness failures in the main sync loop.
	syncLoopMonitor atomic.Value

	// onRepeatedHeartbeatFailure is called when heartbeats fail multiple times.
	onRepeatedHeartbeatFailure func()
}

// Run starts the kubelet. It never returns unless an error occurs or the
// context is cancelled.
func (kl *Kubelet) Run(updates <-chan kubetypes.PodUpdate) {
	ctx := context.Background()
	if kl.logServer == nil {
		kl.logServer = http.StripPrefix("/logs/", http.FileServer(http.Dir("/var/log/")))
	}
	if kl.kubeClient == nil {
		klog.Warning("No api server defined - no node status update will be sent.")
	}

	// Start the cloud-provider sync manager.
	if kl.cloudResourceSyncManager != nil {
		go kl.cloudResourceSyncManager.Run(wait.NeverStop)
	}

	if err := kl.initializeModules(); err != nil {
		kl.recorder.Eventf(kl.nodeRef, v1.EventTypeWarning, events.KubeletSetupFailed, err.Error())
		klog.ErrorS(err, "Failed to initialize internal modules")
		os.Exit(1)
	}

	// Start volume manager.
	go kl.volumeManager.Run(kl.sourcesReady, wait.NeverStop)

	if kl.kubeClient != nil {
		// Introduce some small jitter to ensure that slow kubelet startup does
		// not bloat node status.
		go wait.JitterUntil(kl.syncNodeStatus, kl.nodeStatusUpdateFrequency, 0.04, true, wait.NeverStop)
		go kl.fastStatusUpdateOnce()
		go kl.nodeLeaseController.Run(context.Background())
	}
	go wait.Until(kl.updateRuntimeUp, 5*time.Second, wait.NeverStop)

	// Set up iptables util rules.
	if kl.makeIPTablesUtilChains {
		kl.initNetworkUtil()
	}

	// Start component sync loops.
	kl.statusManager.Start()
	kl.probeManager.Start()

	// Start syncing RuntimeClasses if enabled.
	if kl.runtimeClassManager != nil {
		kl.runtimeClassManager.Start(wait.NeverStop)
	}

	// Start the pod lifecycle event generator (PLEG).
	kl.pleg.Start()

	// Start the eviction manager.
	kl.evictionManager.Start(kl.StatsProvider, kl.GetActivePods, kl.podResourcesAreReclaimed, evictionMonitoringPeriod)

	// Start the node shutdown manager.
	kl.shutdownManager.Start()

	// Main sync loop -- processes pod updates forever.
	kl.syncLoop(ctx, updates, kl)
}

// syncPod is the transaction script for syncing a single pod:
// it compares desired vs actual state and calls the container runtime to
// create, start, restart, or remove containers as needed.
func (kl *Kubelet) syncPod(ctx context.Context, updateType kubetypes.SyncPodType, pod, mirrorPod *v1.Pod, podStatus *kubecontainer.PodStatus) (isTerminal bool, err error) {
	klog.V(4).InfoS("syncPod enter", "pod", klog.KObj(pod), "podUID", pod.UID, "updateType", updateType)
	defer func() {
		klog.V(4).InfoS("syncPod exit", "pod", klog.KObj(pod), "podUID", pod.UID, "isTerminal", isTerminal)
	}()

	// Generate the API-level pod status from the runtime's pod status.
	apiPodStatus := kl.generateAPIPodStatus(pod, podStatus, false)

	// Persist updated status to the status manager (which syncs it to the API server).
	existingStatus, ok := kl.statusManager.GetPodStatus(pod.UID)
	if !ok || !isPodStatusByKubeletEqual(&existingStatus, &apiPodStatus) || updateType == kubetypes.SyncPodSync {
		if kl.podWorkers.CouldHaveRunningContainers(pod.UID) {
			kl.statusManager.SetPodStatus(pod, apiPodStatus)
		}
	}

	// If the pod has already been terminated, signal that.
	if apiPodStatus.Phase == v1.PodSucceeded || apiPodStatus.Phase == v1.PodFailed {
		return true, nil
	}

	// Sync pod via the container runtime.
	result := kl.containerRuntime.SyncPod(ctx, pod, podStatus, kl.getPullSecretsForPod(pod), kl.backOff)
	kl.processKubeletEventsFromPodSync(pod, result)
	return false, result.Error()
}
