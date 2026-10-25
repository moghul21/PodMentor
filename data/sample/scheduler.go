/*
Copyright 2014 The Kubernetes Authors.

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

// Source: https://github.com/kubernetes/kubernetes/blob/master/pkg/scheduler/scheduler.go
// Obtained: 2026-10-25 -- Apache License 2.0
// Representative excerpt for the PodMentor dataset sample.

// Package scheduler watches for new unscheduled pods and attempts to find
// nodes that they fit on, then writes bindings back to the API server.
package scheduler

import (
	"context"
	"fmt"
	"time"

	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/util/wait"
	clientset "k8s.io/client-go/kubernetes"
	"k8s.io/klog/v2"

	"k8s.io/kubernetes/pkg/scheduler/framework"
	"k8s.io/kubernetes/pkg/scheduler/metrics"
	"k8s.io/kubernetes/pkg/scheduler/profile"
)

// Scheduler watches for new unscheduled pods. It attempts to find nodes that
// they fit on and writes bindings back to the api server.
type Scheduler struct {
	Cache internalcache.Cache

	Extenders []framework.Extender

	// NextPod blocks until the next pod is available for scheduling.
	NextPod func(logger klog.Logger) (*framework.QueuedPodInfo, error)

	// FailureHandler is called upon a scheduling failure.
	FailureHandler FailureHandlerFn

	// SchedulePod tries to schedule the given pod to one of the nodes in the
	// node list. Returns a ScheduleResult on success or an error on failure.
	SchedulePod func(ctx context.Context, fwk framework.Framework, state *framework.CycleState, pod *v1.Pod) (ScheduleResult, error)

	// StopEverything closes this channel when the scheduler is asked to stop.
	StopEverything <-chan struct{}

	// SchedulingQueue holds pods to be scheduled.
	SchedulingQueue internalqueue.SchedulingQueue

	// Profiles are the scheduling profiles (one per scheduler-name).
	Profiles profile.Map

	client clientset.Interface

	nodeInfoSnapshot *internalcache.Snapshot

	percentageOfNodesToScore int32
	nextStartNodeIndex       int
}

// ScheduleResult represents the result of one pod's scheduling cycle.
type ScheduleResult struct {
	// SuggestedHost is the name of the selected node.
	SuggestedHost string
	// EvaluatedNodes is the number of nodes the scheduler evaluated.
	EvaluatedNodes int
	// FeasibleNodes is the number of nodes that satisfied the pod's constraints.
	FeasibleNodes int
	// nominatedNode holds preemption result, if applicable.
	nominatedNode *framework.NominatingInfo
}

// Run begins watching and scheduling. It blocks until the context is done.
func (sched *Scheduler) Run(ctx context.Context) {
	logger := klog.FromContext(ctx)
	sched.SchedulingQueue.Run(logger)

	go wait.UntilWithContext(ctx, sched.scheduleOne, 0)

	<-ctx.Done()
	sched.SchedulingQueue.Close()
}

// scheduleOne runs the full scheduling workflow (filter -> score -> bind)
// for a single pod. It is called serially by the scheduler's main goroutine.
func (sched *Scheduler) scheduleOne(ctx context.Context) {
	logger := klog.FromContext(ctx)
	podInfo, err := sched.NextPod(logger)
	if podInfo == nil || err != nil {
		if err != nil {
			logger.Error(err, "Error while retrieving next pod from scheduling queue")
		}
		return
	}
	pod := podInfo.Pod
	logger = klog.LoggerWithValues(logger, "pod", klog.KObj(pod))

	fwk, err := sched.frameworkForPod(pod)
	if err != nil {
		logger.Error(err, "Error occurred getting framework for pod")
		return
	}
	if sched.skipPodSchedule(ctx, fwk, pod) {
		return
	}

	logger.V(3).Info("Attempting to schedule pod", "pod", klog.KObj(pod))
	start := time.Now()
	state := framework.NewCycleState()

	schedulingCycleCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	// schedulingCycle runs: PreFilter -> Filter -> PreScore -> Score -> Reserve
	scheduleResult, assumedPodInfo, status := sched.schedulingCycle(
		schedulingCycleCtx, state, fwk, podInfo, start, framework.NewPodsToActivate(),
	)
	if !status.IsSuccess() {
		sched.FailureHandler(schedulingCycleCtx, fwk, assumedPodInfo, status, scheduleResult.nominatedNode, start)
		return
	}

	// bindingCycle runs asynchronously: PreBind -> Bind -> PostBind
	go func() {
		bindingCycleCtx, cancel := context.WithCancel(ctx)
		defer cancel()
		metrics.Goroutines.WithLabelValues(metrics.Binding).Inc()
		defer metrics.Goroutines.WithLabelValues(metrics.Binding).Dec()

		status := sched.bindingCycle(bindingCycleCtx, state, fwk, scheduleResult, assumedPodInfo, start, framework.NewPodsToActivate())
		if !status.IsSuccess() {
			sched.handleBindingCycleError(bindingCycleCtx, state, fwk, assumedPodInfo, start, scheduleResult.nominatedNode, status)
		}
	}()
}
