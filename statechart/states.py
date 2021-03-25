# -*- coding: utf-8 -*-
#
# Copyright (c) 2016, Leigh McKenzie
# All rights reserved.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import logging

from statechart.runtime import Metadata


class State:
    """A State is a simple state that has no regions or submachine states.

    Args:
        name (str): State name used to identify this instance for logging.
           A unique name is recommended although not enforced.
        context (Context): The parent context that contains this state.

    Attributes:
        name (str): State name used to identify this instance.
        context (Context): State's parent context.
        verbose (bool): Activates state transition logging.

    Examples:
        * First create the parent context
        statechart = Statechart(name='statechart')

        * Then create the states
        a = State(name='a', context=statechart)
        b = State(name='b', context=statechart)

        * Finally create the transitions between states with any associated
        event triggers, actions or guard conditions.
        Transition(start=a, end=b)

    Note:
        Do not dispatch a synchronous event within the action (enter, do or
        exit) functions. If you need to dispatch an event, do so using the
        async_dispatch function of the statechart.

    Raises:
        RuntimeError: If the parent context is invalid.
            Only a state chart can have no parent context.
    """

    def __init__(self, name, context, verbose=True):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.verbose = verbose

        self.name = name

        """Context can be null only for the statechart"""
        if context is None and (not isinstance(self, Statechart)):
            raise RuntimeError('Context cannot be null')

        self.context = context
        self.transitions = []
        self.active = False

    def entry(self, event):
        """
        An optional action that is executed whenever this state is
        entered, regardless of the transition taken to reach the state. If
        defined, entry actions are always executed to completion prior to any
        internal activity or transitions performed within the state.

        Args:
            event (Event): Event which led to the transition into this state.
        """
        pass

    def do(self, event):
        """
        An optional action that is executed whilst this state is active.
        The execution starts after this state is entered, and stops either by
        itself, or when the state is exited, whichever comes first.

        Starts an async task. When the task is finished, it may fire an event
        to trigger a state transition. If the task is still in progress when
        this state is deactivated it will be cancelled.

        Args:
            event (Event): Event which led to the transition into this state.
        """
        pass

    def exit(self, event):
        """
        An optional action that is executed upon deactivation of this state
        regardless of which transition was taken out of the state. If defined,
        exit actions are always executed to completion only after all
        internal activities and transition actions have completed execution.
        Initiates cancellation of the state do action if it is still running.

        Args:
            event (Event): Event which led to the transition into this state.
        """
        pass

    def add_transition(self, transition):
        """Add a transition from this state.

        Transitions with guards are checked first.

        Args:
            transition (Transition): Transition to add, can be a normal or
                internal transition.

        Raises:
            RuntimeError: If transition is invalid.
        """
        if transition is None:
            raise RuntimeError('Cannot add null transition')

        if transition.guard:
            self.transitions.insert(0, transition)
        else:
            self.transitions.append(transition)

    def activate(self, metadata, event):
        """
        Activate the state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Event which led to the transition into this state.
        """
        if self.verbose:
            self._logger.info('Activate "%s"', self.name)

        self.active = True

        if self.context:
            if not self.context.active:
                raise RuntimeError('Parent state not activated')

            self.context.current_state = self

        if self.entry:
            self.entry(event=event)

        if self.do:
            self.do(event=event)

    def deactivate(self, metadata, event):
        """
        Deactivate the state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Event which led to the transition out of this state.
        """
        if self.verbose:
            self._logger.info('Deactivate "%s"', self.name)

        self.exit(event=event)

        self.active = False

    def dispatch(self, metadata, event):
        """
        Dispatch transition.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Transition event trigger.

        Returns:
            True if transition executed, False if transition not allowed,
            due to mismatched event trigger or failed guard condition.
        """
        self.handle_internal(event)

        status = False

        for transition in self.transitions:
            if transition.execute(metadata=metadata, event=event):
                status = True
                break

        return status

    def handle_internal(self, event):
        """
        Handle an internal event. Override to provide specific behaviour for
        a state.

        Events are routed to all active states from the outside-in before
        processing transitions.

        This is a lightweight implementation of an internal transition without
        strict guard and action semantics.

        Filter internal transitions by checking the event name.

        event (Event): Incoming event to handle.
        """
        pass

    def is_active(self, state_name):
        return self.active and self.name == state_name

    def __repr__(self):
        return '%s(name="%s", active="%r")' % (self.__class__.__name__, self.name, self.active)


class Context(State):
    """
    Domain of the state. Needed for setting up the hierarchy. This class
    needn't be instantiated directly.

    Args:
        name (str): An identifier for the model element.
        context (Context): The parent context that contains this state.
    """

    def __init__(self, name, context):
        super().__init__(name=name, context=context)
        self.initial_state = None
        self.current_state = None
        self.finished = False

    def deactivate(self, metadata, event):
        """
        Deactivate the state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Event which led to the transition out of this state.
        """
        super().deactivate(metadata=metadata, event=event)
        self.current_state = None
        self.finished = False

    def is_active(self, state_name):
        if not self.active:
            return False
        elif self.name == state_name:
            return True
        else:
            return self.current_state.is_active(state_name)

    def __repr__(self):
        return '%s(name="%s", active="%s", current state=%r, finished="%s")' % (
            self.__class__.__name__, self.name, self.active, self.current_state, self.finished)


class FinalState(State):
    """
    A special kind of state signifying that the enclosing composite state or
    the entire state machine is completed.

    A final state cannot have transitions or dispatch other transitions.

    Args:
        context (Context): The parent context that contains this state.

    Raises:
        RuntimeError: If the model is ill-formed by attempting to add a transition directly from
            the final state.
    """

    def __init__(self, context):
        super().__init__(name='Final', context=context)

    def add_transition(self, transition):
        raise RuntimeError('Cannot add a transition from the final state')

    def activate(self, metadata, event):
        super().activate(metadata=metadata, event=event)
        self.context.finished = True

    def deactivate(self, metadata, event):
        super().deactivate(metadata=metadata, event=event)
        self.context.finished = False


class ConcurrentState(State):
    """
    A concurrent state is a state that contains composite state regions,
    activated concurrently.

    Args:
        name (str): An identifier for the model element.
        context (Context): The parent context that contains this state.
    """

    def __init__(self, name, context):
        super().__init__(name, context)
        self.regions = []

    def add_region(self, region):
        """
        Add a new region to the concurrent state.

        Args:
            region (CompositeState): Region to add.
        """
        if isinstance(region, CompositeState):
            self.regions.append(region)
        else:
            raise RuntimeError('A concurrent state can only add composite state regions')

    def activate(self, metadata, event):
        """
        Activate the state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Event which led to the transition into this state.
        """
        super().activate(metadata, event)
        for inactive in [region for region in self.regions if not region.active]:
            # Check if region is activated implicitly via incoming transition.
            inactive.activate(metadata=metadata, event=event)
            inactive.initial_state.activate(metadata=metadata, event=event)

    def deactivate(self, metadata, event):
        """
        Deactivate child states within regions, then overall state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event: Event which led to the transition out of this state.
        """
        if self.verbose:
            self._logger.info('Deactivate "%s"', self.name)

        for region in self.regions:
            if region.active:
                region.deactivate(metadata=metadata, event=event)

        super().deactivate(metadata=metadata, event=event)

    def dispatch(self, metadata, event):
        """
        Dispatch transition.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Transition event trigger.

        Returns:
            True if transition executed, False if transition not allowed,
            due to mismatched event trigger or failed guard condition.
        """
        if not self.active:
            raise RuntimeError('Inactive composite state attempting to dispatch transition')

        self.handle_internal(event)

        dispatched = False

        """ Check if any of the child regions can handle the event """
        for region in self.regions:
            if region.dispatch(metadata=metadata, event=event):
                dispatched = True

        if dispatched:
            return True

        """ Check if this state can handle the event by itself """
        for transition in self.transitions:
            if transition.execute(metadata=metadata, event=event):
                dispatched = True
                break

        return dispatched

    @property
    def finished(self):
        """
        Check if all regions within the concurrent state are finished.

        Returns:
            True if all regions are finished.
        """
        return all(region.finished for region in self.regions)

    def is_active(self, state_name):
        if not self.active:
            return False
        elif self.name == state_name:
            return True
        else:
            return any(region.is_active(state_name) for region in self.regions)

    def __repr__(self):
        return '%s(name="%s", active="%s", regions=%r, finished="%s")' % (
            self.__class__.__name__, self.name, self.active, self.regions, self.finished)


class CompositeState(Context):
    """
    A composite state is a state that contains other state vertices (states,
    pseudostates, etc.).

    Args:
        name (str): An identifier for the model element.
        context (Context): The parent context that contains this state.
    """

    def __init__(self, name, context):
        super().__init__(name=name, context=context)
        self.history_state = None

        if isinstance(context, ConcurrentState):
            context.add_region(self)

    def activate(self, metadata, event):
        """
        Activate the state.

        If the transition being activated leads to this state, activate
        the initial state.

        Args:
            metadata (Metadata): Common statechart metadata.
            event: Event which led to the transition into this state.
        """
        super().activate(metadata=metadata, event=event)

        if metadata.transition and metadata.transition.end is self:
            self.initial_state.activate(metadata=metadata, event=event)

    def deactivate(self, metadata, event):
        """
        Deactivate the state.

        If this state contains a history state, store the currently active
        state in history so it can be restored once the history state is
        activated.

        Args:
            metadata (Metadata): Common statechart metadata.
            event: Event which led to the transition out of this state.
        """
        # If the composite state contains a history pseudostate, preserve the current active child
        # state in history, unless that state is a final state.
        if self.history_state and not (isinstance(self.current_state, FinalState)):
            self.history_state.state = self.current_state

        if self.current_state.active:
            self.current_state.deactivate(metadata=metadata, event=event)

        super().deactivate(metadata=metadata, event=event)

    def dispatch(self, metadata, event):
        """
        Dispatch transition.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Transition event trigger.

        Returns:
            True if transition executed, False if transition not allowed,
            due to mismatched event trigger or failed guard condition.
        """
        if not self.active:
            raise RuntimeError('Inactive composite state attempting to dispatch transition')

        self.handle_internal(event)

        # See if the current child state can handle the event
        if self.current_state is None and self.initial_state:
            self.initial_state.activate(metadata=metadata, event=None)
            self.current_state.activate(metadata=metadata, event=event)

        dispatched = False

        if self.current_state and self.current_state.dispatch(metadata=metadata, event=event):
            dispatched = True

        if dispatched:
            # If the substate dispatched the event and this state is no longer active, return.
            if not self.active:
                return True

            # If the substate dispatched the event and reached a final state, continue to dispatch
            # any default transitions from this state.
            if isinstance(self.current_state, FinalState):
                event = None
            else:
                return True

        # Since none of the child states can handle the event, let this state
        # try handling the event.
        for transition in self.transitions:
            # If transition is local, deactivate current state if transition is allowed.
            if self._is_local_transition(transition) and transition.is_allowed(event=event):
                self.current_state.deactivate(metadata=metadata, event=event)

            if transition.execute(metadata=metadata, event=event):
                return True

        return False

    def _is_local_transition(self, transition):
        """
        Check if a transition is local.

        The transition must meet the following conditions:
         - Not an internal transition.
         - Transition originates from this state, but doesn't leave/deactivate it.

        Returns:
            True if the transition is a local transition, otherwise false.
        """
        if transition.start is transition.end or self in transition.deactivate:
            return False
        else:
            return True


class Statechart(Context):
    """
    The main entry point for using the statechart framework. Contains all
    necessary methods for delegating incoming events to the substates.

    Args:
        name (str): An identifier for the model element.
    """

    def __init__(self, name):
        super().__init__(name=name, context=None)
        self.metadata = Metadata()

    def start(self):
        """
        Initialises the Statechart in the metadata. Sets the start state.

        Ensure the statechart has at least an initial state.

        Raises:
            RuntimeError if the statechart had already been started.
        """
        if self.verbose:
            self._logger.info('Start "%s"', self.name)
        self.active = True
        self.initial_state.activate(metadata=self.metadata, event=None)

    def stop(self):
        """
        Stops the statemachine by deactivating statechart and thus all it's child states.
        """
        if self.verbose:
            self._logger.info('Stop "%s"', self.name)
        self.deactivate(metadata=self.metadata, event=None)

    def deactivate(self, metadata, event):
        """
        Deactivate the statechart.

        Args:
            metadata (Metadata): Common statechart metadata.
            event (Event): Event which led to the transition out of this state.
        """
        if self.verbose:
            self._logger.info('Deactivate "%s"', self.name)
        self.active = False
        self.current_state = None

    def dispatch(self, event):
        """
        Calls the dispatch method on the current state.

        Args:
            event (Event): Transition event trigger.

        Returns:
            True if transition executed.
        """
        self.handle_internal(event=event)

        return self.current_state.dispatch(metadata=self.metadata, event=event)

    def active_states(self):
        states = []

        if self.active:
            states.append(self)
            node = self.current_state

            while node is not None:
                states.append(node)

                if isinstance(node, Context):
                    node = node.current_state
                else:
                    break

        return states

    def is_finished(self):
        return self.finished

    def add_transition(self, transition):
        raise RuntimeError('Cannot add transition to a statechart')

    def entry(self, event):
        raise RuntimeError('Cannot define an entry action for a statechart')

    def do(self, event):
        raise RuntimeError('Cannot define an do action for a statechart')

    def exit(self, event):
        raise RuntimeError('Cannot define an exit action for a statechart')
