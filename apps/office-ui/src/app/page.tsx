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
import { VideoOverlay } from '@/components/VideoOverlay';
import { MediaControls } from '@/components/MediaControls';
import { useApprovals } from '@/hooks/useApprovals';
import { useTaskDispatch } from '@/hooks/useTaskDispatch';
import { useColyseus } from '@/hooks/useColyseus';
import type { PlayerEmoteEvent, ProximityUpdate, WebRTCSignal } from '@/hooks/useColyseus';
import { useAvatarConfig } from '@/hooks/useAvatarConfig';
import { useProximityVideo } from '@/hooks/useProximityVideo';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { ApprovalModal } from '@autoswarm/ui';
import type { CoWebsiteEvent, PopupEvent } from '@/game/PhaserGame';
import type { ApprovalRequest, AvatarConfig } from '@autoswarm/shared-types';
import { getSessionUser } from '@/lib/api';

const WorkflowEditor = dynamic(
  () => import('@/components/workflow-editor/WorkflowEditor').then((m) => ({ default: m.WorkflowEditor })),
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

export default function HomePage() {
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

  const handleProximityUpdate = useCallback((update: ProximityUpdate) => {
    proximityUpdateRef.current(update);
  }, []);

  const handleWebRTCSignal = useCallback((signal: WebRTCSignal) => {
    webrtcSignalRef.current(signal);
  }, []);

  const sessionUser = useMemo(() => getSessionUser(), []);

  const {
    officeState,
    connected: colyseusConnected,
    sessionId,
    sendMove,
    sendChat,
    sendEmote,
    sendAvatarConfig,
    sendSignal,
  } = useColyseus({
    playerName: sessionUser?.name ?? sessionUser?.email ?? 'Tactician',
    onPlayerEmote: handlePlayerEmote,
    onProximityUpdate: handleProximityUpdate,
    onWebRTCSignal: handleWebRTCSignal,
  });

  const {
    peers,
    localStream,
    audioEnabled,
    videoEnabled,
    toggleAudio,
    toggleVideo,
    handleProximityUpdate: videoHandleProximity,
    handleWebRTCSignal: videoHandleSignal,
  } = useProximityVideo({
    localSessionId: sessionId,
    sendSignal,
    enabled: colyseusConnected,
  });

  // Wire up the refs now that both hooks are initialized
  proximityUpdateRef.current = videoHandleProximity;
  webrtcSignalRef.current = videoHandleSignal;
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
  const { config: avatarConfig, saveConfig: saveAvatarConfig, isFirstVisit } = useAvatarConfig();
  const [avatarEditorOpen, setAvatarEditorOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [dispatchPanelOpen, setDispatchPanelOpen] = useState(false);
  const [approvalPanelOpen, setApprovalPanelOpen] = useState(false);
  const [workflowEditorOpen, setWorkflowEditorOpen] = useState(false);
  const [marketplaceOpen, setMarketplaceOpen] = useState(false);
  const [activeApproval, setActiveApproval] = useState<ApprovalRequest | null>(
    null,
  );
  const [coWebsite, setCoWebsite] = useState<CoWebsiteEvent | null>(null);
  const [popup, setPopup] = useState<PopupEvent | null>(null);
  const [playerPosition, setPlayerPosition] = useState<{ x: number; y: number } | null>(null);

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
    setWorkflowEditorOpen(true);
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(false);
  }, []);

  const handleMarketplaceOpen = useCallback(() => {
    setMarketplaceOpen(true);
    setDashboardOpen(false);
    setDispatchPanelOpen(false);
    setApprovalPanelOpen(false);
  }, []);

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

  return (
    <ErrorBoundary>
    <ToastProvider>
    <main className="relative h-screen w-screen overflow-hidden bg-slate-900 scanline-overlay">
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
      />

      <DashboardPanel
        open={dashboardOpen}
        onToggle={() => setDashboardOpen((prev) => { if (!prev) setApprovalPanelOpen(false); return !prev; })}
        departments={officeState?.departments ?? []}
        onNewTask={handleDispatchOpen}
        onOpenMarketplace={handleMarketplaceOpen}
      />

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

      <VideoOverlay peers={peers} localStream={localStream} />
      <MediaControls
        audioEnabled={audioEnabled}
        videoEnabled={videoEnabled}
        onToggleAudio={toggleAudio}
        onToggleVideo={toggleVideo}
        visible={peers.length > 0 || !!localStream}
      />

      <EmotePicker onEmote={handleEmote} />

      <AvatarEditor
        open={avatarEditorOpen}
        initialConfig={avatarConfig}
        onSave={handleAvatarSave}
        onClose={() => setAvatarEditorOpen(false)}
      />

      <button
        onClick={() => setAvatarEditorOpen(true)}
        className="absolute top-4 right-4 z-hud rounded bg-slate-800/90 px-3 py-1 text-xs text-slate-300 retro-btn hover:bg-slate-700"
        aria-label="Open avatar editor"
      >
        Avatar
      </button>

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

      <WorkflowEditor
        open={workflowEditorOpen}
        onClose={() => setWorkflowEditorOpen(false)}
        officeState={officeState}
      />

      <SkillMarketplace
        open={marketplaceOpen}
        onClose={() => setMarketplaceOpen(false)}
      />

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
