'use client';

import dynamic from 'next/dynamic';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { ToastProvider } from '@/components/Toast';
import { HUD } from '@/components/HUD';
import { DashboardPanel } from '@/components/DashboardPanel';
import { TaskDispatchPanel } from '@/components/TaskDispatchPanel';
import { ApprovalPanel } from '@/components/ApprovalPanel';
import { ChatPanel } from '@/components/ChatPanel';
import { EmotePicker } from '@/components/EmotePicker';
import { AvatarEditor } from '@/components/AvatarEditor';
import { CoWebsitePanel } from '@/components/CoWebsitePanel';
import { PopupOverlay } from '@/components/PopupOverlay';
import { SkillMarketplace } from '@/components/SkillMarketplace';
import { CalendarPanel } from '@/components/CalendarPanel';
import { WhiteboardPanel } from '@/components/WhiteboardPanel';
import { DeskInfoPanel } from '@/components/DeskInfoPanel';
import { VideoOverlay } from '@/components/VideoOverlay';
import { MediaControls } from '@/components/MediaControls';
import { RecordingControls } from '@/components/RecordingControls';
import { MeetingNotesPanel } from '@/components/MeetingNotesPanel';
import { DemoBanner } from '@/components/DemoBanner';
import { useApprovals } from '@/hooks/useApprovals';
import { useTaskDispatch } from '@/hooks/useTaskDispatch';
import { useCalendar } from '@/hooks/useCalendar';
import { useMeetingNotes } from '@/hooks/useMeetingNotes';
import { useColyseus } from '@/hooks/useColyseus';
import type { PlayerEmoteEvent, ProximityUpdate, WebRTCSignal, SpotlightActiveEvent } from '@/hooks/useColyseus';
import { useAvatarConfig } from '@/hooks/useAvatarConfig';
import { usePlayerStatus } from '@/hooks/usePlayerStatus';
import { StatusSelector } from '@/components/StatusSelector';
import { MusicStatus } from '@/components/MusicStatus';
import { useProximityVideo } from '@/hooks/useProximityVideo';
import { useRecording } from '@/hooks/useRecording';
import { useWhiteboard } from '@/hooks/useWhiteboard';
import { useSpotlight } from '@/hooks/useSpotlight';
import { useNotifications } from '@/hooks/useNotifications';
import { MegaphoneControls } from '@/components/MegaphoneControls';
import { SpotlightControls } from '@/components/SpotlightControls';
import { SpotlightView } from '@/components/SpotlightView';
import { RoomNavigator } from '@/components/RoomNavigator';
import { SimplifiedView } from '@/components/SimplifiedView';
import { OpsFeed } from '@/components/OpsFeed';
import { MetricsDashboard } from '@/components/MetricsDashboard';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { ApprovalModal } from '@autoswarm/ui';
import type { CoWebsiteEvent, PopupEvent } from '@/game/PhaserGame';
import type { ApprovalRequest, AvatarConfig } from '@autoswarm/shared-types';
import { getSessionUser } from '@/lib/api';

const WorkflowEditor = dynamic(
  () => import('@/components/workflow-editor/WorkflowEditor').then((m) => ({ default: m.WorkflowEditor })),
  { ssr: false },
);

const MapEditor = dynamic(
  () => import('@/components/map-editor/MapEditor').then((m) => ({ default: m.MapEditor })),
  { ssr: false },
);

const PhaserGame = dynamic(() => import('@/game/PhaserGame'), {
  ssr: false,
  loading: () => (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-900">
      <div className="pixel-text text-center">
        <p className="mb-4 text-lg text-indigo-400">LOADING</p>
        <div className="mx-auto h-2 w-48 bg-slate-800 pixel-border">
          <div className="h-full w-1/2 animate-pulse bg-indigo-500" />
        </div>
      </div>
    </div>
  ),
});

export interface OfficeExperienceProps {
  mode: 'live' | 'demo';
}

export function OfficeExperience({ mode }: OfficeExperienceProps) {
  const isDemo = mode === 'demo';

  // Lazy-load gameEventBus ref to bridge emote events to Phaser
  const gameEventBusRef = useRef<{ emit: (event: string, detail: unknown) => void } | null>(null);
  useEffect(() => {
    import('@/game/PhaserGame').then((mod) => {
      gameEventBusRef.current = mod.gameEventBus;
    });
  }, []);

  const handlePlayerEmote = useCallback((event: PlayerEmoteEvent) => {
    gameEventBusRef.current?.emit('player-emote', event);
  }, []);

  // Refs for bridging proximity video callbacks (breaks circular dep between hooks)
  const proximityUpdateRef = useRef<(update: ProximityUpdate) => void>(() => {});
  const webrtcSignalRef = useRef<(signal: WebRTCSignal) => void>(() => {});
  const spotlightActiveRef = useRef<(event: SpotlightActiveEvent) => void>(() => {});

  const handleProximityUpdate = useCallback((update: ProximityUpdate) => {
    proximityUpdateRef.current(update);
  }, []);

  const handleWebRTCSignal = useCallback((signal: WebRTCSignal) => {
    webrtcSignalRef.current(signal);
  }, []);

  const handleSpotlightActive = useCallback((event: SpotlightActiveEvent) => {
    spotlightActiveRef.current(event);
  }, []);

  const sessionUser = useMemo(() => getSessionUser(), []);

  const {
    room: colyseusRoom,
    officeState,
    connected: colyseusConnected,
    sessionId,
    sendMove,
    sendChat,
    sendEmote,
    sendAvatarConfig,
    sendStatus,
    sendSignal,
    sendCompanion,
    sendMusicStatus,
    sendMegaphoneStart,
    sendMegaphoneStop,
    sendSpotlightStart,
    sendSpotlightStop,
    sendLockBubble,
    sendUnlockBubble,
  } = useColyseus({
    playerName: sessionUser?.name ?? sessionUser?.email ?? 'Tactician',
    onPlayerEmote: handlePlayerEmote,
    onProximityUpdate: handleProximityUpdate,
    onWebRTCSignal: handleWebRTCSignal,
    onSpotlightActive: handleSpotlightActive,
  });

  const { status: playerStatus, changeStatus: changePlayerStatus } = usePlayerStatus({
    sendStatus,
    enabled: colyseusConnected,
  });

  // Desktop notifications for chat messages when tab is unfocused
  useNotifications(
    sessionUser?.name ?? sessionUser?.email ?? 'Tactician',
    playerStatus
  );

  const {
    peers,
    localStream,
    audioEnabled,
    videoEnabled,
    screenSharing,
    noiseSuppression,
    toggleAudio,
    toggleVideo,
    toggleScreenShare,
    toggleNoiseSuppression,
    handleProximityUpdate: videoHandleProximity,
    handleWebRTCSignal: videoHandleSignal,
  } = useProximityVideo({
    localSessionId: sessionId,
    sendSignal,
    enabled: colyseusConnected,
    playerStatus,
  });

  const {
    recordingState,
    formattedDuration,
    lastRecordingUrl,
    startRecording,
    stopRecording,
  } = useRecording({ localStream, peers });

  const {
    strokes: whiteboardStrokes,
    tool: whiteboardTool,
    color: whiteboardColor,
    width: whiteboardWidth,
    colors: whiteboardColors,
    widths: whiteboardWidths,
    sendStroke: whiteboardSendStroke,
    clearBoard: whiteboardClear,
    setTool: whiteboardSetTool,
    setColor: whiteboardSetColor,
    setWidth: whiteboardSetWidth,
  } = useWhiteboard({ room: colyseusConnected ? colyseusRoom : null });

  const {
    active: spotlightActive,
    isPresenting: spotlightIsPresenting,
    presenterName: spotlightPresenterName,
    presenterSessionId: spotlightPresenterSessionId,
    startSpotlight,
    stopSpotlight,
    handleSpotlightActive: spotlightHandleActive,
  } = useSpotlight({
    localSessionId: sessionId,
    sendSpotlightStart,
    sendSpotlightStop,
    enabled: colyseusConnected,
  });

  const {
    status: meetingNotesStatus,
    notes: meetingNotes,
    error: meetingNotesError,
    dispatchMeetingNotes,
    reset: resetMeetingNotes,
  } = useMeetingNotes();

  // Wire up the refs now that all hooks are initialized
  proximityUpdateRef.current = videoHandleProximity;
  webrtcSignalRef.current = videoHandleSignal;
  spotlightActiveRef.current = spotlightHandleActive;
  const {
    pendingApprovals,
    approve,
    deny,
    connected: approvalsConnected,
  } = useApprovals();
  const {
    dispatch: dispatchTask,
    status: dispatchStatus,
    error: dispatchError,
    lastDispatchedTask,
    reset: resetDispatch,
  } = useTaskDispatch();
  const {
    events: calendarEvents,
    isBusy: calendarBusy,
    connected: calendarConnected,
    status: calendarStatus,
    error: calendarError,
    connect: connectCalendar,
    disconnect: disconnectCalendar,
    refresh: refreshCalendar,
  } = useCalendar({
    onBusyChange: useCallback((busy: boolean) => {
      if (busy && colyseusConnected) {
        changePlayerStatus('busy');
      }
    }, [colyseusConnected, changePlayerStatus]),
  });
  const { config: avatarConfig, saveConfig: saveAvatarConfig, isFirstVisit } = useAvatarConfig();
  const [avatarEditorOpen, setAvatarEditorOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [dispatchPanelOpen, setDispatchPanelOpen] = useState(false);
  const [approvalPanelOpen, setApprovalPanelOpen] = useState(false);
  const [workflowEditorOpen, setWorkflowEditorOpen] = useState(false);
  const [marketplaceOpen, setMarketplaceOpen] = useState(false);
  const [whiteboardOpen, setWhiteboardOpen] = useState(false);
  const [mapEditorOpen, setMapEditorOpen] = useState(false);
  const [calendarPanelOpen, setCalendarPanelOpen] = useState(false);
  const [meetingNotesPanelOpen, setMeetingNotesPanelOpen] = useState(false);
  const [opsFeedOpen, setOpsFeedOpen] = useState(false);
  const [metricsDashboardOpen, setMetricsDashboardOpen] = useState(false);
  const [activeApproval, setActiveApproval] = useState<ApprovalRequest | null>(
    null,
  );
  const [coWebsite, setCoWebsite] = useState<CoWebsiteEvent | null>(null);
  const [popup, setPopup] = useState<PopupEvent | null>(null);
  const [playerPosition, setPlayerPosition] = useState<{ x: number; y: number } | null>(null);
  const [deskInfo, setDeskInfo] = useState<{ assignedAgentId: string; title: string } | null>(null);
  const [bubbleLocked, setBubbleLocked] = useState(false);
  const [megaphoneActive, setMegaphoneActive] = useState(false);
  const [megaphoneSpeaker, setMegaphoneSpeaker] = useState<string | null>(null);
  const [currentRoom, setCurrentRoom] = useState('office');
  const [companionType, setCompanionType] = useState(() => {
    if (typeof window !== 'undefined') {
      try { return localStorage.getItem('autoswarm:companion-type') ?? ''; } catch { return ''; }
    }
    return '';
  });
  const [musicStatus, setMusicStatus] = useState('');
  const [followingPlayer, setFollowingPlayer] = useState<string | null>(null);
  const [explorerMode, setExplorerMode] = useState(false);
  const [spotlightViewDismissed, setSpotlightViewDismissed] = useState(false);
  const [viewMode, setViewMode] = useState<'game' | 'simple'>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('autoswarm:view-mode') as 'game' | 'simple') ?? 'game';
    }
    return 'game';
  });

  const handleToggleViewMode = useCallback(() => {
    setViewMode((prev) => {
      const next = prev === 'game' ? 'simple' : 'game';
      try { localStorage.setItem('autoswarm:view-mode', next); } catch { /* noop */ }
      return next;
    });
  }, []);

  const handleApprovalOpen = useCallback(
    (agentId: string) => {
      const request = pendingApprovals.find((a) => a.agentId === agentId);
      if (request) {
        setActiveApproval(request);
      }
    },
    [pendingApprovals],
  );

  const handleApprove = useCallback(
    async (requestId: string, feedback?: string): Promise<boolean> => {
      const ok = await approve(requestId, feedback || undefined);
      if (ok) setActiveApproval(null);
      return ok;
    },
    [approve],
  );

  const handleDeny = useCallback(
    async (requestId: string, feedback?: string): Promise<boolean> => {
      const ok = await deny(requestId, feedback || undefined);
      if (ok) setActiveApproval(null);
      return ok;
    },
    [deny],
  );

  const handlePlayerMove = useCallback(
    (x: number, y: number) => {
      sendMove(x, y);
      setPlayerPosition({ x, y });
    },
    [sendMove],
  );

  const handleEmote = useCallback(
    (type: string) => {
      sendEmote(type);
    },
    [sendEmote],
  );

  const handleCoWebsite = useCallback(
    (event: CoWebsiteEvent) => {
      setCoWebsite(event);
    },
    [],
  );

  const handlePopup = useCallback(
    (event: PopupEvent) => {
      setPopup(event);
    },
    [],
  );

  const handleDispatchOpen = useCallback(() => {
    setDashboardOpen(false);
    setApprovalPanelOpen(false);
    setDispatchPanelOpen(true);
  }, []);

  const handleApprovalPanelOpen = useCallback(() => {
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(true);
  }, []);

  const handleBlueprintOpen = useCallback(() => {
    if (isDemo) return; // No workflow editor in demo
    setWorkflowEditorOpen(true);
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(false);
  }, [isDemo]);

  const handleGenerateNotes = useCallback(() => {
    if (lastRecordingUrl) {
      void dispatchMeetingNotes(lastRecordingUrl);
      setMeetingNotesPanelOpen(true);
    }
  }, [lastRecordingUrl, dispatchMeetingNotes]);

  const handleMarketplaceOpen = useCallback(() => {
    if (isDemo) return; // No marketplace in demo
    setMarketplaceOpen(true);
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(false);
  }, [isDemo]);

  const handleMapEditorOpen = useCallback(() => {
    if (isDemo) return; // No map editor in demo
    setMapEditorOpen(true);
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(false);
  }, [isDemo]);

  const handleDispatchClose = useCallback(() => {
    setDispatchPanelOpen(false);
  }, []);

  const handleAvatarSave = useCallback(
    (config: AvatarConfig) => {
      saveAvatarConfig(config);
      sendAvatarConfig(JSON.stringify(config));
      setAvatarEditorOpen(false);
      // Forward avatar config to Phaser
      gameEventBusRef.current?.emit('avatar-config', config);
    },
    [saveAvatarConfig, sendAvatarConfig],
  );

  // Open avatar editor on first visit
  useEffect(() => {
    if (isFirstVisit && colyseusConnected) {
      setAvatarEditorOpen(true);
    }
  }, [isFirstVisit, colyseusConnected]);

  // Send avatar config to server when connected
  useEffect(() => {
    if (colyseusConnected && avatarConfig) {
      sendAvatarConfig(JSON.stringify(avatarConfig));
      gameEventBusRef.current?.emit('avatar-config', avatarConfig);
    }
  }, [colyseusConnected, avatarConfig, sendAvatarConfig]);

  // Reset spotlight dismissed state when spotlight becomes inactive
  useEffect(() => {
    if (!spotlightActive) {
      setSpotlightViewDismissed(false);
    }
  }, [spotlightActive]);

  // Send companion type to server when connected
  useEffect(() => {
    if (colyseusConnected && companionType) {
      sendCompanion(companionType);
    }
  }, [colyseusConnected, companionType, sendCompanion]);

  // Listen for desk info events from game
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    import('@/game/PhaserGame').then((mod) => {
      cleanup = mod.gameEventBus.on('open_desk_info', (detail: unknown) => {
        const event = detail as { title: string; assignedAgentId: string };
        setDeskInfo({ assignedAgentId: event.assignedAgentId, title: event.title });
      });
    });
    return () => cleanup?.();
  }, []);

  // Listen for whiteboard open events from game
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    import('@/game/PhaserGame').then((mod) => {
      cleanup = mod.gameEventBus.on('open_whiteboard', () => {
        setWhiteboardOpen(true);
        setDashboardOpen(false);
        setDispatchPanelOpen(false);
        setApprovalPanelOpen(false);
      });
    });
    return () => cleanup?.();
  }, []);

  // Listen for follow/explorer mode events from game
  useEffect(() => {
    const cleanups: Array<() => void> = [];
    import('@/game/PhaserGame').then((mod) => {
      cleanups.push(
        mod.gameEventBus.on('follow-status', (detail: unknown) => {
          const { following, name } = detail as { following: boolean; name: string };
          setFollowingPlayer(following ? name : null);
        }),
        mod.gameEventBus.on('explorer-mode', (detail: unknown) => {
          setExplorerMode(detail as boolean);
        }),
      );
    });
    return () => cleanups.forEach((c) => c());
  }, []);

  // Listen for megaphone and room transition events
  useEffect(() => {
    const cleanups: Array<() => void> = [];
    import('@/game/PhaserGame').then((mod) => {
      cleanups.push(
        mod.gameEventBus.on('room_transition', (detail: unknown) => {
          const { roomId } = detail as { roomId: string };
          setCurrentRoom(roomId);
          // Update URL for map loading
          const url = new URL(window.location.href);
          url.searchParams.set('map', roomId);
          window.history.replaceState({}, '', url.toString());
        }),
      );
    });
    // Listen for megaphone broadcasts from Colyseus
    // This is done in the useColyseus onMessage handler
    return () => cleanups.forEach((c) => c());
  }, []);

  return (
    <ErrorBoundary>
    <ToastProvider>
    <main className="relative h-screen w-screen overflow-hidden bg-slate-900 scanline-overlay">
      {isDemo && <DemoBanner />}

      {viewMode === 'game' ? (
        <>
          <PhaserGame
            onApprovalOpen={handleApprovalOpen}
            officeState={officeState}
            sessionId={sessionId}
            onPlayerMove={handlePlayerMove}
            onEmote={handleEmote}
            onCoWebsite={handleCoWebsite}
            onPopup={handlePopup}
            onDispatchOpen={handleDispatchOpen}
            onBlueprintOpen={handleBlueprintOpen}
          />

          <HUD
            activeAgentCount={officeState?.activeAgentCount ?? 0}
            pendingApprovalCount={pendingApprovals.length}
            computeTokens={officeState ? { used: 0, limit: 10000 } : undefined}
            colyseusConnected={colyseusConnected}
            approvalsConnected={approvalsConnected}
            departments={officeState?.departments ?? []}
            playerPosition={playerPosition}
            userName={sessionUser?.name ?? sessionUser?.email ?? null}
            onApprovalClick={handleApprovalPanelOpen}
            followingPlayer={followingPlayer}
            explorerMode={explorerMode}
            viewMode={viewMode}
            onToggleViewMode={handleToggleViewMode}
          />

          {/* Ops controls (left side) — hidden in demo */}
          {!isDemo && (
            <div className="absolute top-4 left-4 z-hud flex gap-1">
              <button
                onClick={() => { setOpsFeedOpen((prev) => !prev); setDashboardOpen(false); }}
                className={`rounded px-2 py-1 font-mono text-[8px] retro-btn ${
                  opsFeedOpen ? 'bg-emerald-600 text-white' : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
                }`}
                aria-label="Toggle ops feed"
              >
                Ops Feed
              </button>
              <button
                onClick={() => { setMetricsDashboardOpen(true); }}
                className="rounded bg-slate-800/90 px-2 py-1 font-mono text-[8px] text-slate-300 retro-btn hover:bg-slate-700"
                aria-label="Open metrics dashboard"
              >
                Metrics
              </button>
            </div>
          )}

          {!isDemo && (
            <OpsFeed
              open={opsFeedOpen}
              onClose={() => setOpsFeedOpen(false)}
            />
          )}

          <DashboardPanel
            open={dashboardOpen}
            onToggle={() => setDashboardOpen((prev) => { if (!prev) setApprovalPanelOpen(false); return !prev; })}
            departments={officeState?.departments ?? []}
            onNewTask={handleDispatchOpen}
            onOpenMarketplace={isDemo ? undefined : handleMarketplaceOpen}
            onOpenMapEditor={isDemo ? undefined : handleMapEditorOpen}
          />

          <ApprovalPanel
            open={approvalPanelOpen}
            onClose={() => setApprovalPanelOpen(false)}
            pendingApprovals={pendingApprovals}
            onApprove={handleApprove}
            onDeny={handleDeny}
            connected={approvalsConnected}
          />

          <ChatPanel
            messages={officeState?.chatMessages ?? []}
            onSend={sendChat}
            localSessionId={sessionId ?? ''}
          />

          <VideoOverlay peers={peers} localStream={localStream} screenSharing={screenSharing} />
          <MediaControls
            audioEnabled={audioEnabled}
            videoEnabled={videoEnabled}
            onToggleAudio={toggleAudio}
            onToggleVideo={toggleVideo}
            screenSharing={screenSharing}
            onToggleScreenShare={toggleScreenShare}
            bubbleLocked={bubbleLocked}
            noiseSuppression={noiseSuppression}
            onToggleNoiseSuppression={toggleNoiseSuppression}
            onToggleLockBubble={() => {
              if (bubbleLocked) {
                sendUnlockBubble();
                setBubbleLocked(false);
              } else {
                sendLockBubble();
                setBubbleLocked(true);
              }
            }}
            visible={peers.length > 0 || !!localStream}
          />
          <RecordingControls
            recordingState={recordingState}
            formattedDuration={formattedDuration}
            onStart={startRecording}
            onStop={stopRecording}
            visible={peers.length > 0 || !!localStream}
            lastRecordingUrl={lastRecordingUrl}
            onGenerateNotes={handleGenerateNotes}
          />
          <MegaphoneControls
            active={megaphoneActive}
            speakerName={megaphoneSpeaker}
            isLocalSpeaker={megaphoneActive && megaphoneSpeaker === (sessionUser?.name ?? sessionUser?.email ?? null)}
            onStart={() => { sendMegaphoneStart(); setMegaphoneActive(true); setMegaphoneSpeaker(sessionUser?.name ?? sessionUser?.email ?? 'You'); }}
            onStop={() => { sendMegaphoneStop(); setMegaphoneActive(false); setMegaphoneSpeaker(null); }}
            visible={peers.length > 0 || !!localStream}
          />
          <SpotlightControls
            active={spotlightActive}
            presenterName={spotlightPresenterName}
            isPresenting={spotlightIsPresenting}
            onStart={startSpotlight}
            onStop={stopSpotlight}
            visible={peers.length > 0 || !!localStream}
          />
          {!spotlightViewDismissed && (
            <SpotlightView
              active={spotlightActive}
              isPresenting={spotlightIsPresenting}
              presenterName={spotlightPresenterName}
              presenterSessionId={spotlightPresenterSessionId}
              peers={peers}
              onClose={() => setSpotlightViewDismissed(true)}
            />
          )}
          <RoomNavigator
            currentRoom={currentRoom}
            onChangeRoom={(roomId) => setCurrentRoom(roomId)}
            visible={colyseusConnected}
          />

          <EmotePicker onEmote={handleEmote} />

          <AvatarEditor
            open={avatarEditorOpen}
            initialConfig={avatarConfig}
            onSave={handleAvatarSave}
            onClose={() => setAvatarEditorOpen(false)}
            companionType={companionType}
            onCompanionChange={(type) => {
              setCompanionType(type);
              sendCompanion(type);
              try { localStorage.setItem('autoswarm:companion-type', type); } catch { /* noop */ }
            }}
          />

          <button
            onClick={() => setAvatarEditorOpen(true)}
            className="absolute top-4 right-4 z-hud rounded bg-slate-800/90 px-3 py-1 text-xs text-slate-300 retro-btn hover:bg-slate-700"
            aria-label="Open avatar editor"
          >
            Avatar
          </button>

          {/* Right-side controls — hide calendar in demo */}
          <div className="absolute top-14 right-4 z-hud flex flex-col gap-1">
            {!isDemo && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setCalendarPanelOpen((prev) => !prev);
                    setDashboardOpen(false);
                    setDispatchPanelOpen(false);
                    setApprovalPanelOpen(false);
                  }}
                  className={`rounded bg-slate-800/90 px-3 py-1 text-xs retro-btn ${
                    calendarConnected
                      ? calendarBusy
                        ? 'text-amber-400 hover:bg-amber-900/40'
                        : 'text-emerald-400 hover:bg-emerald-900/40'
                      : 'text-slate-300 hover:bg-slate-700'
                  }`}
                  aria-label="Toggle calendar panel"
                >
                  Calendar{calendarBusy ? ' (busy)' : ''}
                </button>
              </div>
            )}
            <StatusSelector
              currentStatus={playerStatus}
              onStatusChange={changePlayerStatus}
            />
            <MusicStatus
              currentStatus={musicStatus}
              onStatusChange={(status) => {
                setMusicStatus(status);
                sendMusicStatus(status);
              }}
            />
          </div>

          <CoWebsitePanel
            url={coWebsite?.url ?? null}
            title={coWebsite?.title ?? ''}
            onClose={() => setCoWebsite(null)}
          />

          <PopupOverlay
            open={!!popup}
            title={popup?.title ?? ''}
            content={popup?.content ?? ''}
            onClose={() => setPopup(null)}
          />

          <DeskInfoPanel
            open={!!deskInfo}
            onClose={() => setDeskInfo(null)}
            assignedAgentId={deskInfo?.assignedAgentId ?? ''}
            deskTitle={deskInfo?.title ?? 'Desk'}
            departments={officeState?.departments ?? []}
          />
        </>
      ) : (
        <SimplifiedView
          departments={officeState?.departments ?? []}
          pendingApprovals={pendingApprovals}
          chatMessages={officeState?.chatMessages ?? []}
          onSendChat={sendChat}
          onApprove={handleApprove}
          onDeny={handleDeny}
          onDispatchTask={handleDispatchOpen}
          onOpenMarketplace={isDemo ? undefined : handleMarketplaceOpen}
          onToggleViewMode={handleToggleViewMode}
          colyseusConnected={colyseusConnected}
          approvalsConnected={approvalsConnected}
        />
      )}

      {/* Shared modals — available in both game and simplified view */}
      <TaskDispatchPanel
        open={dispatchPanelOpen}
        onClose={handleDispatchClose}
        onDispatch={dispatchTask}
        status={dispatchStatus}
        error={dispatchError}
        lastDispatchedTask={lastDispatchedTask}
        departments={officeState?.departments ?? []}
        onReset={resetDispatch}
      />

      {!isDemo && (
        <WorkflowEditor
          open={workflowEditorOpen}
          onClose={() => setWorkflowEditorOpen(false)}
          officeState={officeState}
        />
      )}

      <MeetingNotesPanel
        open={meetingNotesPanelOpen}
        onClose={() => { setMeetingNotesPanelOpen(false); resetMeetingNotes(); }}
        status={meetingNotesStatus}
        notes={meetingNotes}
        error={meetingNotesError}
      />

      {!isDemo && (
        <SkillMarketplace
          open={marketplaceOpen}
          onClose={() => setMarketplaceOpen(false)}
        />
      )}

      {!isDemo && (
        <CalendarPanel
          open={calendarPanelOpen}
          onClose={() => setCalendarPanelOpen(false)}
          events={calendarEvents}
          isBusy={calendarBusy}
          connected={calendarConnected}
          status={calendarStatus}
          error={calendarError}
          onConnect={connectCalendar}
          onDisconnect={disconnectCalendar}
          onRefresh={refreshCalendar}
        />
      )}

      <WhiteboardPanel
        open={whiteboardOpen}
        onClose={() => setWhiteboardOpen(false)}
        strokes={whiteboardStrokes}
        tool={whiteboardTool}
        color={whiteboardColor}
        width={whiteboardWidth}
        colors={whiteboardColors}
        widths={whiteboardWidths}
        onSendStroke={whiteboardSendStroke}
        onClear={whiteboardClear}
        onToolChange={whiteboardSetTool}
        onColorChange={whiteboardSetColor}
        onWidthChange={whiteboardSetWidth}
      />

      {!isDemo && (
        <MapEditor
          open={mapEditorOpen}
          onClose={() => setMapEditorOpen(false)}
        />
      )}

      {!isDemo && (
        <MetricsDashboard
          open={metricsDashboardOpen}
          onClose={() => setMetricsDashboardOpen(false)}
        />
      )}

      {activeApproval && (
        <ApprovalModal
          open={!!activeApproval}
          onOpenChange={(open) => {
            if (!open) setActiveApproval(null);
          }}
          request={activeApproval}
          onApprove={handleApprove}
          onDeny={handleDeny}
        />
      )}
    </main>
    </ToastProvider>
    </ErrorBoundary>
  );
}
