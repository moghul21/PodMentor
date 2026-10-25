/*
Copyright 2017 The Kubernetes Authors.

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

// Source: https://github.com/kubernetes/kubernetes/blob/master/pkg/controller/nodelifecycle/node_lifecycle_controller.go
// Obtained: 2026-10-25 -- Apache License 2.0
// Representative excerpt for the PodMentor dataset sample.

package nodelifecycle

import (
	"context"
	"fmt"
	"sync"
	"time"

	v1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	utilruntime "k8s.io/apimachinery/pkg/util/runtime"
	clientset "k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/cache"
	"k8s.io/client-go/util/workqueue"
	"k8s.io/klog/v2"
)

const (
	// NodeEvictionPeriod controls how frequently NodeController will try to
	// evict Pods from non-responsive Nodes.
	NodeEvictionPeriod = 100 * time.Millisecond

	// nodeEvictionRate is the number of nodes per second on which pods are
	// deleted in case of node failure when a zone is healthy.
	nodeEvictionRate = 0.1

	// secondaryNodeEvictionRate is the number of nodes per second on which
	// pods are deleted in case of node failure when a zone becomes unhealthy.
	secondaryNodeEvictionRate = 0.01

	// largeClusterThreshold is the number of nodes above which the cluster
	// is considered large for the eviction algorithm purposes.
	largeClusterThreshold = 50

	// unhealthyZoneThreshold is the fraction of nodes in a zone below which
	// the zone is considered unhealthy.
	unhealthyZoneThreshold = 0.55
)

// ZoneState is the state of a given zone.
type ZoneState string

const (
	stateInitial           = ZoneState("Initial")
	stateNormal            = ZoneState("Normal")
	stateFullDisruption    = ZoneState("FullDisruption")
	statePartialDisruption = ZoneState("PartialDisruption")
)

// Controller manages node life cycle: it monitors node health and evicts pods
// from nodes that are not responding.
type Controller struct {
	kubeClient clientset.Interface

	// per-zone eviction queues
	zonePodEvictor map[string]*RateLimitedTimedQueue
	zoneStates     map[string]ZoneState

	nodeLister          corelisters.NodeLister
	podLister           corelisters.PodLister
	nodeInformerSynced  cache.InformerSynced

	nodeMonitorGracePeriod time.Duration
	podEvictionTimeout     time.Duration
	nodeMonitorPeriod      time.Duration

	nodeHealthMap *nodeHealthMap
	evictorLock   sync.RWMutex

	nodeUpdateQueue workqueue.RateLimitingInterface
}

// doEvictionPass iterates over the eviction queues and removes pods from nodes
// that have been unreachable longer than podEvictionTimeout.
func (nc *Controller) doEvictionPass(ctx context.Context) {
	nc.evictorLock.Lock()
	defer nc.evictorLock.Unlock()
	for k := range nc.zonePodEvictor {
		nc.zonePodEvictor[k].Try(func(value TimedValue) (bool, time.Duration) {
			node, err := nc.nodeLister.Get(value.Value)
			if apierrors.IsNotFound(err) {
				klog.Warningf("Node %v no longer present in nodeLister!", value.Value)
				return true, 0
			} else if err != nil {
				klog.Warningf("Failed to get Node %v from the nodeLister: %v", value.Value, err)
				return false, 50 * time.Millisecond
			}
			_, err = evictPods(ctx, nc.kubeClient, node, nc.podLister)
			if err != nil {
				utilruntime.HandleError(fmt.Errorf("unable to evict node %+v: %v", node.Name, err))
				return false, 0
			}
			return true, 0
		})
	}
}
