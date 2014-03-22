from . import GEScenario
from GamePlay.Utils.GEPlayerTracker import GEPlayerTracker
from Utils.GETimer import TimerTracker, Timer

import GEPlayer, GEUtil, GEMPGameRules, GEGlobal, GEEntity

USING_API = GEGlobal.API_VERSION_1_1_1

'''
This mode is based on Mefy's MOHAA "Freeze Tag" Mode.

This mode script uses lots of code from the "You Only Live Twice" mode script.

The grave stones were created by Kraid.

Translators: 
 French: namajnaG,
 German: Kraid,
 Spanish: VGF
 Italian: Matteo Bini

Supported Languages: English,French,German,Spanish,Polish and Italian.

@author(s): Joe
@version: Alpha 1.10 Z.G
'''
class DieAnotherDay(GEScenario):
    version = "Alpha 1.10 Z.G WIP"
    
    trEliminated = "eliminated"
    trSpawned = "spawned"
    
    eliminatedPlayerHUDUpdateDelay = 1.0
    
    maxSeperationBetweenGroundAndJumpingPlayer = 45.00
    maxSeperationDistanceBetweenGroundAndGroundedPlayer = 8.04
    
    #--------------- GUI Constants:
    mColour = GEUtil.CColor(0,150,255,255)
    jColour = GEUtil.Color(255,0,0,255)

    mRERadarColour = GEUtil.CColor(118,255,227,255) 
    mUsedRERadarColour= GEUtil.CColor(143,167,255,255)

    jRERadarColour = GEUtil.Color(255,118,118,255)
    jUsedRERadarColour= GEUtil.Color(255,80,39,255)

    RQPositionColour = GEUtil.Color(255,255,0,255)
    
    #Progress Bar Indexs
    mSCountPBIndex = 0
    jSCountPBIndex = 1
    resurrectionPBIndex = 2
    
    survivorCountPBY = 0.01
    spectatorSCountPBY = 0.12
    resBarY = 0.765
    
    mSurvivorCountPBX = 0.30
    survivorCountSeperationDistance = 0.20
    
    sCountChannel = 1
    specSCountChannel = 2
    resQueueMessageChannel = 3

    def __init__( self ):
        super( DieAnotherDay, self ).__init__()
        
        self.resurrectionTime = 5.0 #Server owners who want to change this must use this CVAR: dad_resurrectionDuration
        self.usedRELocationRevealTime = 10.0 #Server owners who want to change this must use this CVAR: dad_usedRELocationRevealDuration
        
        self.radar = None
        self.timerTracker = TimerTracker(self)
        self.pltracker = GEPlayerTracker( self )
        self.tokenManager = GEMPGameRules.GetTokenMgr()
        
        self.resurrections = DieAnotherDay.ResurrectionDict(self)
        self.REs = DieAnotherDay.REDict(self)
        
        self.playersLRRTargetMonitor = {}
        self.playersExemptFromSucideEliminaton = []
        
        self.waitingForPlayers = False
        
        self.mResurrectionQueue = []
        self.jResurrectionQueue = []

        self.resurrectedPlayers = []
                
        self.mSurvivorCountDisplay = DieAnotherDay.SurvivorCountDisplay(self,GEGlobal.TEAM_MI6)
        self.jSurvivorCountDisplay = DieAnotherDay.SurvivorCountDisplay(self,GEGlobal.TEAM_JANUS)
        
        self.eliminatedPlayerCount = 0
        
    def Cleanup( self ):
        super( DieAnotherDay, self ).Cleanup()
        
        self.resurrections.cleanup()
        self.REs.cleanup()
        self.resurrections = None
        self.REs = None
        
        '''
        Object References
        '''
        self.pltracker = None
        self.timerTracker = None
        self.tokenManager = None
        self.radar = None
                
        '''
        Collection References
        '''
        
        self.playersExemptFromSucideEliminaton = None
        
        #Eliminated player collections
        self.mResurrectionQueue = None
        self.jResurrectionQueue = None
        
        self.resurrectedBots = None
        
        #Collections related to resurrection RE entities
        self.playersLRRTargetMonitor = None
        
        self.resurrectedPlayers = None
    
    #1. Callback functions:
    def GetPrintName( self ):
        return "#GES_GP_DAD_NAME"
    
    def GetGameDescription( self ):
        return "#GES_GP_DAD_NAME"
    
    def GetScenarioHelp( self, help_obj ):
        help_obj.SetDescription( "#GES_GP_DAD_HELP" )
        
    def GetTeamPlay( self ):
        return GEGlobal.TEAMPLAY_ALWAYS
    
    def OnLoadGamePlay( self ):
        GEUtil.PrecacheModel("models/gameplay/gravestone.mdl")
        
        #TODO When the GE:S version after 4.2.3 is released with the nessecary translations, enable the use of these translations:
        self.CreateCVar("dad_resurrectionDuration", "5", "The duration of resurrections in DAD mode." )
        self.CreateCVar("dad_usedRELocationRevealDuration","10","How long the location of a used grave stone will be shown to both sides.")
        
        self.radar = GEMPGameRules.GetRadar()
        self.radar.SetForceRadar(True)
    
    def OnCVarChanged( self, name, oldvalue, newvalue ):
        if name == "dad_resurrectionDuration": self.resurrectionTime = float(newvalue)
        elif name == "dad_usedRELocationRevealDuration": self.usedRELocationRevealTime = float(newvalue)

    def OnPlayerConnect( self, player ):
        self.pltracker.SetValue(player,self.trSpawned,False)
        self.pltracker.SetValue(player,self.trEliminated,False)

    def OnPlayerDisconnect( self, player ):
        team = player.GetTeamNumber()
        
        if team != GEGlobal.TEAM_SPECTATOR:
            self.resurrections.playerHasDisconnected(player)
            wasEliminated = self.isEliminatedPlayer(player)
            
            #Update the displayed survivor count for their old team:
            if team == GEGlobal.TEAM_MI6: self.mSurvivorCountDisplay.OnPlayerLeaveTeam(wasEliminated)
            else: self.jSurvivorCountDisplay.OnPlayerLeaveTeam(wasEliminated)
            
            if wasEliminated:
                self.removePlayerFromTeamsRQueue(player,team)
                self.resurrections.deleteNotInUseRE(team)
        
        if player in self.resurrectedPlayers: self.resurrectedPlayers.remove(player)
    
    def OnPlayerSay(self,player,text):
        if text == "!voodoo":
            if not self.isEliminatedPlayer(player) and player.GetTeamNumber() != GEGlobal.TEAM_SPECTATOR:
                if not self.playersLRRTargetMonitor.has_key(player):
                    hitEntity = self.getEntHitByLRRLaser(player)
                    if hitEntity != None:
                        if hitEntity.GetClassname() == "ge_capturearea":
                            if hitEntity.GetTeamNumber() == player.GetTeamNumber() and self.REs.areaUsable(hitEntity): self.beginREInteraction(player,hitEntity,False)
        
        if text == "!gesrocks":
            GEUtil.DevWarning("self.eliminatedPlayerCount:" + str(self.eliminatedPlayerCount) + "\n") #TODO joe
        
        return True
        
    def OnCaptureAreaSpawned( self, area ):
        areasTeam = area.GetTeamNumber()
        
        #Record that the RE area has been spawned
        self.REs.areaSpawned(area)
        
        #Add the RE's position to the radar.
        self.radar.AddRadarContact(area,GEGlobal.RADAR_TYPE_OBJECTIVE,True,"sprites/hud/radar/RE",self.getSidesRadarColour(areasTeam,True))
        
        #Setup radar icon for idle RE:
        self.radar.SetupObjective(area,areasTeam,"", "",self.getSidesColour(areasTeam),200,False)
        
        #If nesscary, move the spawned RE:
        ID = area.GetGroupName()
        if self.REs.needsToBeMoved(ID): self.REs.moveToDeathLocation(ID)
        
        #TODO Prevent 2 REs from overlapping
        #TODO Prevent RE from spawning in doorway.
        
    def OnCaptureAreaEntered(self,REArea,player,token):
        if REArea.GetTeamNumber() == player.GetTeamNumber() and self.REs.areaUsable(REArea): self.beginREInteraction(player,REArea,True)
        
    def OnCaptureAreaExited(self,REArea,player ):
        if REArea.GetTeamNumber() == player.GetTeamNumber(): self.resurrections.playerHasExitedFriendlyREArea(REArea,player)        

    def OnPlayerObserver(self,player):
        GEUtil.DevWarning("OnPlayerObserver ----- \n\n") #TODO joe
        oldTeam = self.pltracker.GetValue(player,"team")
        currentTeam = player.GetTeamNumber()
        self.pltracker.SetValue(player,"team",currentTeam)
        
        if currentTeam == GEGlobal.TEAM_SPECTATOR and (oldTeam == GEGlobal.TEAM_MI6 or oldTeam == GEGlobal.TEAM_JANUS):
            self.removePlayerFromTeamsRQueue(player,oldTeam)
            self.resurrections.deleteNotInUseRE(oldTeam)
            GEUtil.RemoveHudProgressBar(player, DieAnotherDay.resQueueMessageChannel)
            wasEliminated = (self.pltracker.GetValue(player,"elimination_cause") == "killed")
            
            if oldTeam == GEGlobal.TEAM_MI6:
                self.mSurvivorCountDisplay.OnPlayerBecomesSpectator(wasEliminated)
            elif oldTeam == GEGlobal.TEAM_JANUS:
                self.jSurvivorCountDisplay.OnPlayerBecomesSpectator(wasEliminated)
                            
    def observerTeamChangeCheck(self,timer,update_type,player):
        if update_type == Timer.UPDATE_FINISH:
            GEUtil.DevWarning("observerTeamChangeCheck\n")
            oldTeam = self.pltracker.GetValue(player,"team")
            currentTeam = player.GetTeamNumber()
            self.pltracker.SetValue(player,"team",currentTeam)
            
            if currentTeam != oldTeam:
                if oldTeam == GEGlobal.TEAM_MI6 or oldTeam == GEGlobal.TEAM_JANUS:
                    self.removePlayerFromTeamsRQueue(player, oldTeam)
                    self.resurrections.deleteNotInUseRE(oldTeam)
                    GEUtil.RemoveHudProgressBar(player, DieAnotherDay.resQueueMessageChannel)
                    
                if currentTeam == GEGlobal.TEAM_MI6 or currentTeam == GEGlobal.TEAM_JANUS:
                    self.REs.spawnNewResurrectionEntity(player,currentTeam)
                    self.addPlayerToResurrectionQueue(player, currentTeam)
                    self.drawEliminatedPlayerResQueueMessage(player)
                
                self.mSurvivorCountDisplay.OnPlayerJoinedTeam(True,True,oldTeam,currentTeam)
                self.jSurvivorCountDisplay.OnPlayerJoinedTeam(True,True,oldTeam,currentTeam)

    def OnPlayerSpawn(self,player):
        team = player.GetTeamNumber()
        
        if team != GEGlobal.TEAM_SPECTATOR:
            if player.IsInitialSpawn(): 
                self.pltracker.SetValue(player,self.trSpawned,True)
                self.pltracker.SetValue(player,"team",player.GetTeamNumber())
                self.pltracker.SetValue(player,"elimination_cause","")
            
            if player in self.resurrectedPlayers: self.resurrectedPlayers.remove(player)
            else:
                #Should the new team member who has spawned be eliminated?
                wasEliminated = self.isEliminatedPlayer(player)
                GEUtil.DevWarning("---eliminatedPlayerCount = " + str(self.eliminatedPlayerCount))#TODO Joe
                if self.eliminatedPlayerCount != 0: self.OnPlayerEliminated(player)
                
                #Else:
                newTeam = player.GetTeamNumber()
                oldTeam = self.pltracker.GetValue(player,"team")
                
                if newTeam == oldTeam: oldTeam = -1
                
                if oldTeam == GEGlobal.TEAM_MI6 or newTeam == GEGlobal.TEAM_MI6: 
                    self.mSurvivorCountDisplay.OnPlayerJoinedTeam(wasEliminated,self.isEliminatedPlayer(player),oldTeam,newTeam)
                if oldTeam == GEGlobal.TEAM_JANUS or newTeam == GEGlobal.TEAM_JANUS:
                    self.jSurvivorCountDisplay.OnPlayerJoinedTeam(wasEliminated,self.isEliminatedPlayer(player),oldTeam,newTeam)
                
                if oldTeam != newTeam: self.pltracker.SetValue(player,"team",newTeam)
             
        GEUtil.PopupMessage(player,"#GES_GP_DAD_NAME","#GES_GP_DAD_FIRST_SPAWN_INSTRUCTIONS")
        GEUtil.HudMessage(player, "This unfinished DAD version is not meant to be played, it probably has bugs.",-1,-1, GEUtil.CColor(255, 0, 0,255),10.00,20)
    
    def OnRoundEnd( self ):
        #End and delete all timers first to prevent post round reset timer callback errors:
        self.resurrections.cancelResurrections()
        for timer in self.timerTracker.timers: timer.Stop()
        self.timerTracker.RemoveTimer(None)
        
        #Reset everything else:
        self.eliminatedPlayerCount = 0
        self.REs.deleteAll()
        
        self.mSurvivorCountDisplay.hide()
        self.jSurvivorCountDisplay.hide()

        del self.resurrectedPlayers[:]
        del self.playersExemptFromSucideEliminaton[:]
        del self.mResurrectionQueue[:]
        del self.jResurrectionQueue[:]
        
        self.radar.DropAllContacts()
    
    def OnRoundBegin( self ):
        if not self.waitingForPlayers:
            for i in range( 32 ):
                if not GEPlayer.IsValidPlayerIndex( i ):
                    continue
                self.pltracker.SetValue( GEPlayer.GetMPPlayer( i ), self.trEliminated, False )
    
            GEMPGameRules.ResetAllPlayerDeaths()
            GEMPGameRules.ResetAllPlayersScores()
        
        self.mSurvivorCountDisplay.OnRoundStart()
        self.jSurvivorCountDisplay.OnRoundStart()
        
        GEUtil.HudMessage(None, "This unfinished DAD version is not meant to be played, it probably has bugs.",-1,-1, GEUtil.CColor(255, 0, 0,255),10.00,20)

    #TODO Allow players to eliminate their team mates because otherwise they could help their team mates by respawning them:
    def OnPlayerKilled( self, victim, killer, weapon ):
        GEUtil.DevWarning("OnPlayerKilled\n") #TODO Joe
        super( DieAnotherDay, self ).OnPlayerKilled( victim, killer, weapon )
        victimsTeam = victim.GetTeamNumber()
        killersTeam = None
        if killer != None: killersTeam = killer.GetTeamNumber
        
        #1.If the killed player was resurrecting team mates, cancel their resurrections
        self.resurrections.playerHasBeenKilled(victim)
        
        #2. [If not killed by team mate]
        if victimsTeam != killersTeam or victim == killer: #self.respondToTeamMateElimination()
            #3.[Not Caused By Team Change Suicide]
            if(victim == killer and victim in self.playersExemptFromSucideEliminaton):
                self.playersExemptFromSucideEliminaton.remove(victim)
                return
            #4. Announce the elimination
            if killer != None:
                GEUtil.EmitGameplayEvent( "DieAnotherDay_elimination","%s" % victim.GetPlayerName(),"%i" % victim.GetTeamNumber(),"%s" % killer.GetPlayerName())
                if victim.GetTeamNumber() == GEGlobal.TEAM_MI6:GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_MI6_PLAYER_ELIMINATED",victim.GetPlayerName())
                else: GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_JANUS_PLAYER_ELIMINATED",victim.GetPlayerName())
            #5. Eliminate the player
            self.OnPlayerEliminated(victim,killer,weapon)
            
            #6. Update the displayed survivor count for the victim's team:
            if victimsTeam == GEGlobal.TEAM_MI6: self.mSurvivorCountDisplay.OnTeamMemberEliminated()
            else: self.jSurvivorCountDisplay.OnTeamMemberEliminated()
    
    def OnPlayerEliminated(self,player,killer=None,weapon=None):
        team = player.GetTeamNumber()
        #1.Eliminate the player
        self.eliminatePlayer(player)
        self.eliminatedPlayerCount += 1
        #If the round won't end because of this elimination:
        if GEMPGameRules.GetNumInRoundTeamPlayers(team) - 1 > 0:
            #2.Record that the player has been eliminated and prevent them from respawning:
            if killer: self.pltracker.SetValue(player,"elimination_cause","killed")
            else: self.pltracker.SetValue(player,"elimination_cause","rules")
            self.addPlayerToResurrectionQueue(player,team)
            #3.Draw the eliminated player's resurrection queue message on their screen.
            self.drawEliminatedPlayerResQueueMessage(player)
            #4.Spawn a RE at the dead player's death location or the ground beneath if they died in the air. If they died above the jump height their RE will be spawned at a spawn point.
            self.REs.spawnNewResurrectionEntity(player,team,self.decideWhereREWillBeLocated(player,killer,weapon))

    def OnThink(self):
        if GEMPGameRules.GetNumActivePlayers() < 2:
            self.waitingForPlayers = True
            return

        if self.waitingForPlayers:
            self.waitingForPlayers = False
            GEUtil.HudMessage( None, "#GES_GP_GETREADY", -1, -1, GEUtil.CColor( 255, 255, 255, 255 ), 2.5 )
            GEMPGameRules.EndRound( False )

        #Check to see if the round is over:
        #check to see if each team has a player...
        inPlayMPlayers = []
        inPlayJPlayers = []

        for i in range( 32 ):
            if not GEPlayer.IsValidPlayerIndex( i ):
                continue

            player = GEPlayer.GetMPPlayer( i )
            if self.IsInPlay( player ):
                if player.GetTeamNumber() == GEGlobal.TEAM_MI6:
                    inPlayMPlayers.append( player )
                elif player.GetTeamNumber() == GEGlobal.TEAM_JANUS:
                    inPlayJPlayers.append( player )

        numMI6Players = len(inPlayMPlayers)
        numJanusPlayers = len(inPlayJPlayers)

        if numMI6Players == 0 and numJanusPlayers == 0: GEMPGameRules.EndRound()
        elif numMI6Players == 0 and numJanusPlayers > 0: self.teamWins(GEGlobal.TEAM_JANUS)
        elif numMI6Players > 0 and numJanusPlayers == 0: self.teamWins(GEGlobal.TEAM_MI6)
            
    def teamWins(self,teamNumber):
        team = GEMPGameRules.GetTeam(teamNumber)
        team.IncrementMatchScore( 5 )
        GEMPGameRules.SetTeamWinner(team)
        GEMPGameRules.EndRound()
        
    def CanPlayerChangeTeam(self,player,oldTeam,newTeam):
        if oldTeam != GEGlobal.TEAM_SPECTATOR and newTeam != GEGlobal.TEAM_SPECTATOR: 
            self.playersExemptFromSucideEliminaton.append(player)
        if self.isEliminatedPlayer(player) and (newTeam == GEGlobal.TEAM_MI6 or newTeam == GEGlobal.TEAM_JANUS):
            GEUtil.DevWarning("**** self.isEliminatedPlayer(player) and (newTeam == GEGlobal.TEAM_MI6 or newTeam == GEGlobal.TEAM_JANUS): ****\n")
            teamChangeCheckTimer = DieAnotherDay.ExtCallbackTimer(self.timerTracker,self.observerTeamChangeCheck,player)
            teamChangeCheckTimer.start(1)
        return True
        
    #2. Info Getting Functions:
    @staticmethod
    def getEntHitByLRRLaser(user):
        traceEndVector = GEUtil.VectorMA(user.GetEyePosition(),user.GetAimDirection(),40000.00)
        return GEUtil.Trace(user.GetEyePosition(),traceEndVector,GEUtil.TraceOpt.CAPAREA | GEUtil.TraceOpt.PLAYER | GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.WEAPON,user)
    
    def IsInPlay( self, player ):
        return player.GetTeamNumber() is not GEGlobal.TEAM_SPECTATOR and self.pltracker.GetValue( player, self.trSpawned ) and not self.pltracker.GetValue( player, self.trEliminated )
    
    def getSidesColour(self,side):
        if side == GEGlobal.TEAM_MI6: return self.mColour
        else: return self.jColour

    def getSidesRadarColour(self,side,isREIcon=True):
        if side == GEGlobal.TEAM_MI6: 
            if isREIcon: return DieAnotherDay.mRERadarColour
            else: return DieAnotherDay.mUsedRERadarColour
        else:
            if isREIcon: return DieAnotherDay.jRERadarColour
            else: return DieAnotherDay.jUsedRERadarColour

    def getSidesResQueue(self,team):
        if team == GEGlobal.TEAM_MI6: return self.mResurrectionQueue
        else: return self.jResurrectionQueue         

    def updateResQueuePlayerCount(self,team):
        resQueue = self.getSidesResQueue(team)
        
        for player in resQueue:
            self.drawEliminatedPlayerResQueueMessage(player,resQueue)

    def drawEliminatedPlayerResQueueMessage(self,player,resQueue=None):
        if self.playerNotBot(player):
            if resQueue == None: 
                resQueue = self.getSidesResQueue(player.GetTeamNumber())
            
            GEUtil.InitHudProgressBar(player, DieAnotherDay.resQueueMessageChannel, title="#GES_GP_DAD_RESURRECTION_QUEUE_POSITION", flags=GEGlobal.HUDPB_SHOWVALUE, max_value=len(resQueue), x=-1, y=0.75, color=DieAnotherDay.RQPositionColour, curr_value=resQueue.index(player))            
            
#     player_or_team -- GEPlayer.CGEPlayer or Team Number
#     index -- int
#     title -- str
#     flags -- int
#     max_value -- float
#     x -- float
#     y -- float
#     wide -- int
#     tall -- int
#     color -- GEUtil.Color
#     curr_value -- float
            
    @staticmethod
    def playerNotBot(player):
        return player.__class__.__name__ != "CGEBotPlayer"
    
    def addPlayerToResurrectionQueue(self,player,team):
        teamsRQueue = None
        
        if team == GEGlobal.TEAM_MI6: teamsRQueue = self.mResurrectionQueue
        else: teamsRQueue = self.jResurrectionQueue
        
        #Prevent players from having to wait behind bots in their side's resurrection queue:
        #Player Insertion:
        if self.playerNotBot(player):
            positionOfBotNearestRQueueFront = self.getPositionOfBotNearestQueueFront(teamsRQueue)
            
            if positionOfBotNearestRQueueFront == -1: teamsRQueue.append(player)
            else:
                bot = teamsRQueue[positionOfBotNearestRQueueFront]
                teamsRQueue.insert(positionOfBotNearestRQueueFront,player)
                teamsRQueue.remove(bot)
                teamsRQueue.append(bot)
            
        #Bot Insertion:
        else: teamsRQueue.append(player)
        
    def getPositionOfBotNearestQueueFront(self,rQueue):
        for player in rQueue: 
            if self.playerNotBot(player) == False: return rQueue.index(player)
        return -1
        
    def removePlayerFromTeamsRQueue(self,player,team):
        rQueue = None
        if team == GEGlobal.TEAM_MI6: rQueue = self.mResurrectionQueue
        else: rQueue = self.jResurrectionQueue
        
        if player in rQueue: 
            rQueue.remove(player)
            self.updateResQueuePlayerCount(team)
        
    def delayedResurrectionPBRemovalIfNoActiveResurrectionsAfterDelay(self,timer,update_type,player):
        if update_type == Timer.UPDATE_FINISH:
            if self.resurrections.getPlayersResurrectionCount(player) == 0: GEUtil.RemoveHudProgressBar(player,DieAnotherDay.resurrectionPBIndex)
        
    #5. RE Functions:
    #6. Functions Related To Resurrections:
    def eliminatePlayer(self,player):
        self.pltracker.SetValue(player,self.trEliminated,True)
    
    def beginREInteraction(self,player,REArea,proximityInteraction):
        resurrection = self.resurrections.getREResurrection(player,REArea.GetGroupName())
        RE = self.REs.getRE(REArea.GetGroupName())
        if resurrection == None: self.resurrections.startNewResurrection(RE,player,proximityInteraction)
        else:
            if proximityInteraction: resurrection.proximityEnabled = True
            else: resurrection.LRREnabled = True
    
    def resurrectPlayerFromTeamIfTeamHasEliminatedPlayers(self,resurrector):
        areasTeam = resurrector.GetTeamNumber()
        
        #Choose player to be resurrected
        resurrectedPlayer = None
        if areasTeam == GEGlobal.TEAM_MI6 and len(self.mResurrectionQueue) != 0: resurrectedPlayer = self.mResurrectionQueue.pop(0)
        elif areasTeam == GEGlobal.TEAM_JANUS and len(self.jResurrectionQueue) != 0: resurrectedPlayer = self.jResurrectionQueue.pop(0) 
        
        if resurrectedPlayer != None:
            self.pltracker.SetValue(resurrectedPlayer,self.trEliminated,False)
            self.eliminatedPlayerCount -= 1
            self.updateResQueuePlayerCount(areasTeam)
            return resurrectedPlayer
        return None
        
    def CanPlayerRespawn(self,player):
        if self.isEliminatedPlayer(player):
            player.SetScoreBoardColor(GEGlobal.SB_COLOR_ELIMINATED)
            return False
        else:
            player.SetScoreBoardColor( GEGlobal.SB_COLOR_NORMAL )
            return True
    
    def decideWhereREWillBeLocated(self,victim,killer,weapon):
        whenSpawnedMoveRETo = None
        
        if self.isPlayerTouchingGround(victim):
            #kill command? player_hurt map trigger?
            if killer != None and weapon != None: whenSpawnedMoveRETo = victim.GetAbsOrigin()
            
        #else: whenSpawnedMoveRETo = self.getVecForGroundBeneathJumpingPlayer(victim)
    
        return whenSpawnedMoveRETo    
    
    def isPlayerTouchingGround(self,player):
        origin = player.GetAbsOrigin()
        endV = GEUtil.VectorMA(origin,GEUtil.Vector(0,0,-1),self.maxSeperationDistanceBetweenGroundAndGroundedPlayer)
        returned = GEUtil.Trace(origin,endV,GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.PLAYER,player)#GE:S bot bug: can't ignore bot player unless PLAYER is traceable.
        
        #In case the trace went through a gap between steps:
        if returned == None:
            origin.__setitem__(1,origin.__getitem__(1) + 5.00)
            endV = GEUtil.VectorMA(origin,GEUtil.Vector(0,0,-1),50.00)
            returned = GEUtil.Trace(origin,endV,GEUtil.TraceOpt.WORLD | GEUtil.TraceOpt.PLAYER,player)
        
        return returned != None
    
    #------ Team Change Response Functions
    def isEliminatedPlayer(self,player):
        return self.pltracker.GetValue(player,self.trEliminated)
    
    def playerWantsToBecomeSpectator(self,player,oldTeam):
        return

    #------------------------------
    
    class SurvivorCountDisplay:
        def __init__(self,DADP,teamP):
            self.DAD = DADP
            self.team = teamP
            self.title = None
            self.x = None
            self.y = DieAnotherDay.survivorCountPBY
            self.index = None
            self.colour = self.DAD.getSidesColour(self.team)
            self.shown = False
            self.playerCount = 0
            self.survivorCount = 0
            self.delayedTotalUpdateInProgress = False
            
            if self.team == GEGlobal.TEAM_MI6:
                self.title = "MI6:"
                self.index = DieAnotherDay.mSCountPBIndex
                self.x = DieAnotherDay.mSurvivorCountPBX
            else:
                self.title = "Janus:"
                self.index = DieAnotherDay.jSCountPBIndex
                self.x = DieAnotherDay.mSurvivorCountPBX + DieAnotherDay.survivorCountSeperationDistance
        
        def allPlayersAlive(self):
            return self.playerCount == self.survivorCount
        
        def show(self):
            GEUtil.InitHudProgressBar(None,self.index,self.title,GEGlobal.HUDPB_SHOWVALUE,self.playerCount,self.x,self.y,120,60,self.colour,self.survivorCount)
            self.shown = True
        
        def hide(self):
            GEUtil.RemoveHudProgressBar(None,self.index)
            self.shown = False
            
        def totalUpdate(self):
            self.hide()
            self.show()
            
        def playerCountHasIncreased(self):
            newPlayerCount = GEMPGameRules.GetNumInRoundTeamPlayers(self.team)
            return self.playerCount < newPlayerCount
        
        def playerCountHasDecreased(self):
            newPlayerCount = GEMPGameRules.GetNumInRoundTeamPlayers(self.team)
            return self.playerCount > newPlayerCount
            
        def playerCountUpdate(self):
            newPlayerCount = GEMPGameRules.GetNumInRoundTeamPlayers(self.team)
            if self.playerCount != newPlayerCount:
                GEUtil.InitHudProgressBar(None,self.index,self.title,GEGlobal.HUDPB_SHOWVALUE,self.playerCount,self.x,self.y,120,60,self.colour,self.survivorCount)
                self.shown = True
            
        def updateSurvivorCount(self):
            GEUtil.UpdateHudProgressBar(None,self.index,self.survivorCount)
            
        def delayedTotalUpdateCB(self,timer,update_type):
            if update_type == Timer.UPDATE_FINISH:
                self.playerCount = GEMPGameRules.GetNumActiveTeamPlayers(self.team)
                self.survivorCount = GEMPGameRules.GetNumInRoundTeamPlayers(self.team)
                self.delayedTotalUpdateInProgress = False
                self.show()    
        
        def delayedTotalUpdate(self):
            #if self.delayedTotalUpdateInProgress == False: 
            self.delayedTotalUpdateInProgress = True
            self.DAD.timerTracker.OneShotTimer(2.0,self.delayedTotalUpdateCB)
        #----------- Callback functions:
        def OnRoundStart(self):
            self.delayedTotalUpdate()
            
        def OnPlayerJoinedTeam(self,wasEliminated,isEliminated,oldTeam,newTeam):
            GEUtil.DevWarning("1.OnPlayerJoinedTeam()\n")
            if oldTeam == self.team:
                self.playerCount -= 1
                if not wasEliminated: self.survivorCount -= 1
            elif newTeam == self.team:
                self.playerCount += 1
                if not isEliminated: self.survivorCount += 1
                
            self.totalUpdate()
            
        def OnPlayerLeaveTeam(self,wasEliminated):
            GEUtil.DevWarning("2. OnPlayerLeaveTeam()\n")
            self.playerCount -= 1
            if not wasEliminated: self.survivorCount -= 1
            self.totalUpdate()
        
        def OnPlayerBecomesSpectator(self,wasEliminated):
            GEUtil.DevWarning("3. OnPlayerBecomesSpectator()\n")
            self.playerCount -= 1
            if not wasEliminated: self.survivorCount -= 1
            self.totalUpdate()
        
        def OnTeamMemberEliminated(self):
            GEUtil.DevWarning("4. OnTeamMemberEliminated()\n")
            self.survivorCount -= 1
            self.updateSurvivorCount()
            
        def OnTeamMemberResurrected(self):
            GEUtil.DevWarning("5. OnTeamMemberResurrected()\n")
            self.survivorCount += 1
            self.updateSurvivorCount()
    
    '''
        This class is responsible for detecting when a player has stopped aiming a LRR beam at a RE they are using.
        
        The resurrection class uses self.targetMissed to find out when a monitor has detected this and it will then stop the target monitor.
        
        @Client class: Resurrection
    '''    
    class LRRTargetMonitor:
        drawnLaserDuration = 0.4
        aimCheckRate = 0.2
        
        def __init__(self,resurrectionP):
            self.targetMissed = False
            self.DAD = resurrectionP.DAD
            self.resurrection = resurrectionP
            self.secsSinceLaserDrawn = 0
            
            self.targetCheckTimer = None            
            self.targetCheckTimer = self.DAD.timerTracker.CreateTimer("LRRTargetMonitor:" + self.resurrection.user.GetPlayerName())
            self.targetCheckTimer.SetAgeRate(1.0,0)
            self.targetCheckTimer.SetUpdateCallback(self.monitorPlayersLRRTarget,self.aimCheckRate)
            
            self.laserColour = self.DAD.getSidesColour(self.resurrection.user.GetTeamNumber())
            self.DAD.playersLRRTargetMonitor[self.resurrection.user] = self
            self.REContactVector = GEUtil.VectorMA(self.resurrection.RE.location,GEUtil.Vector(0,0,1),40)
        
        def start(self):
            self.targetCheckTimer.Start()
            
        def stop(self):
            self.targetCheckTimer.Stop()
        
        def delete(self):
            self.targetCheckTimer.Stop()
            self.DAD.timerTracker.RemoveTimer(self.targetCheckTimer.GetName())
            del self.DAD.playersLRRTargetMonitor[self.resurrection.user]
        
        def monitorPlayersLRRTarget(self,timer,update_type):
            #1.Draw the first temporary beam to the RE
            if update_type == Timer.UPDATE_START: self.drawLaser()
            elif update_type == Timer.UPDATE_RUN:
                #2. [Player's LRR beam is still hitting the friendly RE]
                if self.resurrection.RE.isEntity(DieAnotherDay.getEntHitByLRRLaser(self.resurrection.user)):
                    #3. Draw a new temporary beam to the RE
                    self.drawLaser()
                #Exception: Record that this monitor's target has been missed before its associated resurrection ended.
                else: 
                    self.DAD.resurrections.playerHasCeasedTargettingRE(self.resurrection)
                    
            
        def drawLaser(self):
            GEUtil.CreateTempEnt(GEUtil.TempEnt.BEAM,origin=self.resurrection.user.GetEyePosition(),end=self.REContactVector,duration=self.drawnLaserDuration + 0.2,color=self.laserColour)                             

    class ExtCallbackTimer():
            instanceID = 0
            def __init__(self,timerTrackerP,extCallbackP,runParameterP,callbackRate=1.0,ageRate=1.0):
                self.extCallback = extCallbackP
                self.runParameter = runParameterP
                
                self.timerTracker = timerTrackerP
                instanceIDBefore = DieAnotherDay.ExtCallbackTimer.instanceID
                DieAnotherDay.ExtCallbackTimer.instanceID = instanceIDBefore + 1
                self.timer = self.timerTracker.CreateTimer("CallbackTimer:" + str(instanceIDBefore))
                self.timer.SetUpdateCallback(self.TimerTick,callbackRate)
                self.timer.SetAgeRate(ageRate)
                
            def TimerTick(self,timer,update_type):
                self.extCallback(timer,update_type,self.runParameter)
                if update_type == Timer.UPDATE_FINISH: self.timerTracker.RemoveTimer(self.timer.GetName())
                
            def start(self,duration):
                self.timer.Start(duration)
                
            def stop(self):
                self.timer.Stop()

    class REDict:
        def __init__(self,DADP):
            self.unusedAreaID = 0
            self.DAD = DADP
            self.REs = {}
            
        def cleanup(self):
            self.DAD = None
            for RE in self.REs.values(): RE.cleanup()
            self.REs = None
            
        def getRE(self,ID):
            return self.REs[ID]
            
        def flagREAsUsed(self,ID):
            self.REs[ID].used = True
            
        def hasREBeenUsed(self,ID):
            return self.REs[ID].used
            
        def getListOfTeamsREs(self,teamP):
            teamsREs = []
            for RE in self.REs.values():
                if RE.team == teamP: teamsREs.append(RE)
                
            return teamsREs
        
        def areaSpawned(self,area):
            self.REs[area.GetGroupName()].areaSpawned(area)
            
        def spawnNewResurrectionEntity(self,victim,team,afterSpawnMoveTo=None):
            newAreasID = str(self.unusedAreaID)
            self.unusedAreaID += 1
            self.spawnResurrectionEntity(newAreasID,team,afterSpawnMoveTo)
        
        def spawnResurrectionEntity(self,areaID,team,afterSpawnMoveTo=None):
            skinNumber = 1
            if team == GEGlobal.TEAM_MI6: skinNumber = 0
            
            self.DAD.tokenManager.SetupCaptureArea(areaID, 
                                                   radius = 35,
                                                   model="models/gameplay/gravestone.mdl",
                                                   limit=1,
                                                   #glow_color=self.DAD.getSidesColour(team),
                                                   #glow_dist=0,
                                                   skin=skinNumber,
                                                   rqd_team=team)
            
            self.REs[areaID] = DieAnotherDay.REDict.RE(self.DAD,areaID,team)
            
            if afterSpawnMoveTo != None: self.REs[areaID].setMoveToLocation(afterSpawnMoveTo)
            
        def makeREGlow(self,RE):
            self.DAD.tokenManager.SetupCaptureArea(RE.GetGroupName(),glow_dist=350)
            
        def disableREGlow(self,RE):
            self.DAD.tokenManager.SetupCaptureArea(RE.GetGroupName(),glow_dist=0)
#         
        def areaUsable(self,area):
            ID = area.GetGroupName()
            if ID in self.REs.keys():
                RE = self.REs[ID]
                return RE.disabled == False and RE.used == False
                
            return False
            
        def deleteRE(self,ID):
            del self.REs[ID]
            self.DAD.tokenManager.RemoveCaptureArea(ID)
            
        def doesREExsist(self,ID):
            return ID in self.REs.keys()
            
        def deleteREAfterDelay(self,ID,delay):
            timer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.deleteREAfterDelayCallback,ID)
            timer.start(delay)
            
        def deleteREAfterDelayCallback(self,timer,update_type,ID):
            if update_type == Timer.UPDATE_FINISH: self.deleteRE(ID)
            
        def deleteAll(self):
            for RE in self.REs.values(): RE.delete()
            self.REs = {}
            self.unusedAreaID = 0
            
        def getTeamsRELocations(self,teamP):
            foundLocations = []
            for RE in self.REs.values():
                if RE.team == teamP: foundLocations.append(RE.getLocation())
            return foundLocations
            
        def needsToBeMoved(self,ID):
            return self.REs[ID].needsToBeMoved()
        
        def moveToDeathLocation(self,ID):
            self.REs[ID].move()
            
        def isPulsating(self,ID):
            return self.REs[ID].isPulsating()
             
        def startPulsatingRings(self,ID):
            self.REs[ID].pulsate()
         
        def stopPulsatingRings(self,ID):
            self.REs[ID].stopPulsating()
            
        class RE:
            creationOrderNumber = 0
            
            def __init__(self,DADP,IDP,teamP):
                self.disabled = True
                self.DAD = DADP
                
                self.ID = IDP
                self.team = teamP
                self.areasHandle = None
                self.pulseTimer = None
                self.needsToBeMovedTo = None
                self.used = False
                self.location = None
                self.userCount = 0
                
            def cleanup(self):
                self.areasHandle = None
                self.pulseTimer = None
                self.needsToBeMovedTo = None
                self.location = None
                
            def delete(self):
                if self.pulseTimer != None: self.pulseTimer.stop()
                self.DAD.tokenManager.RemoveCaptureArea(self.ID)
                self.cleanup()
                
            def areaSpawned(self,area):
                self.areasHandle = GEEntity.EntityHandle(area)
                self.pulseTimer = DieAnotherDay.REDict.RE.RingPulseTimer(self.DAD,area)
                self.location = area.GetAbsOrigin()
                self.disabled = False
                
            def makeInvisible(self):
                self.DAD.tokenManager.SetupCaptureArea(self.ID,model="",glow_dist=0)
                
            def isEntity(self,entity):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.isEntity() failed: area handle returned None.\n")
                    return None
                
                return area == entity
                
            def clearObjective(self):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.clearObjective() failed: area handle returned None.\n")
                    return None
                
                self.DAD.radar.ClearObjective(area)
                
            def setupObjective(self,team):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.setupObjective() failed: area handle returned None.\n")
                    return None
                
                if team == None: team = area.GetTeamNumber()
                self.DAD.radar.SetupObjective(area,team,"","",self.DAD.getSidesColour(team),200,True)
                
            def setupYellowObjective(self):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.setupYellowObjective() failed: area handle returned None.\n")
                    return None
                
                self.DAD.radar.SetupObjective(area,area.GetTeamNumber(),"","",DieAnotherDay.RQPositionColour,200,True)
                
            def setMoveToLocation(self,location):
                self.needsToBeMovedTo = location
                
            def needsToBeMoved(self):
                return self.needsToBeMovedTo != None
            
            def move(self):
                if self.needsToBeMovedTo == None:
                    GEUtil.DevWarning("RE.move() failed: needsToBeMovedTo = None\n")
                    return False
                
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.move() failed: area handle returned None.\n")
                    return False
                
                area.SetAbsOrigin(self.needsToBeMovedTo)
                self.location = self.needsToBeMovedTo
                self.pulseTimer.origin = self.location
                self.needsToBeMovedTo = None
                
            def changeRadarIconAfterDelay(self,icon,colour,delay):
                timer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.changRadarIconAfterDelayCB,{"icon":icon,"colour":colour})
                timer.start(delay)
            
            def changRadarIconAfterDelayCB(self,timer,update_type,parameters):
                if update_type == Timer.UPDATE_FINISH: self.changeRadarIcon(parameters["icon"],parameters["colour"])
                
            def changeRadarIcon(self,newIcon,colour):
                area = self.areasHandle.Get()
                if area == None:
                    GEUtil.DevWarning("RE.changeRadarIcon() failed: area handle returned None.\n")
                    return False
                
                self.DAD.radar.DropRadarContact(area)
                self.DAD.radar.AddRadarContact(area,GEGlobal.RADAR_TYPE_OBJECTIVE,True,newIcon,colour)
                
            def pulsate(self):
                self.pulseTimer.start()
                
            def stopPulsating(self):
                self.pulseTimer.stop()
                
            def isPulsating(self):
                return self.pulseTimer.isPulsating()
            
            ''''
            This class is responsible for drawing pulsating rings around active REs
            '''
            class RingPulseTimer:
                def __init__(self,DADP,area):
                    self.DAD = DADP
                    self.timer = self.DAD.timerTracker.CreateTimer("RingPulseTimer:" + area.GetGroupName())
                    self.timer.SetUpdateCallback(self.TimerTick,0.5)
                    self.timer.SetAgeRate(1.0,0) 
                    self.PULSE_COLOUR = self.DAD.getSidesColour(area.GetTeamNumber())
                    self.origin = area.GetAbsOrigin()
                    
                def start(self):
                    self.timer.Start()
                    
                def stop(self):
                    self.timer.Stop()
                    
                def isPulsating(self):
                    return self.timer.state != Timer.STATE_STOP
                    
                def TimerTick( self, timer, update_type ):
                    if GEMPGameRules.IsIntermission() == False and update_type != Timer.UPDATE_STOP and update_type == Timer.UPDATE_RUN: self.DrawNewRing()
                
                def DrawNewRing( self ):
                    GEUtil.CreateTempEnt(GEUtil.TempEnt.RING,origin=self.origin,framerate=15,duration=2,speed=10,width=0.33,amplitude=0.0,radius_start=0,radius_end=220,color=self.PULSE_COLOUR)
           
                def delete(self):
                    self.DAD.timerTracker.RemoveTimer(self.timer.GetName())

    class ResurrectionDict:
        def __init__(self,DADP):
            self.DAD = DADP
            self.resurrections = {}
            
        def cleanup(self):
            self.DAD = None
            self.resurrections = None
            
        def isResurrectionKnown(self,resurrectionP):
            return self.resurrections.has_key(resurrectionP.getID())
        
        def startNewResurrection(self,RE,user,startedAtCloseRange):
            newResurrection = DieAnotherDay.Resurrection(self.DAD,RE,user,startedAtCloseRange)
            idP = newResurrection.getID()
            self.resurrections[idP] = newResurrection
            self.resurrections[idP].start()
            return newResurrection
        
        def deleteNotInUseRE(self,team):
            #Find not in use REs:
            teamsREs = self.DAD.REs.getListOfTeamsREs(team)
            for resurrection in self.resurrections.values():
                if resurrection.RE in teamsREs: teamsREs.remove(resurrection.RE)
                
            #Delete a not in use RE:
            if len(teamsREs) != 0: 
                self.DAD.REs.deleteRE(teamsREs.pop().ID)
                return True
            else: return False
            
        def delete(self,resurrection):
            del self.resurrections[resurrection.getID()]
                
        def getREsResurrections(self,REP):
            found = []
            
            for resurrection in self.resurrections.values():
                if resurrection.RE == REP: 
                    found.append(resurrection)
            return found
            
        def getPlayersResurrectionCount(self,player):
            return len(self.getPlayersResurrections(player))
        
        def cancelREResurrections(self,IDP,ignoreID=-1):
            for resurrection in self.resurrections.values():
                if resurrection.RE.ID == IDP and resurrection.ID != ignoreID: resurrection.stop()
                
        def cancelResurrections(self):
            for resurrection in self.resurrections.values(): resurrection.resurrectionFailed()
        
        def getREResurrection(self,player,REID):
            for resurrection in self.resurrections.values():
                if resurrection.user == player and resurrection.RE.ID == REID: return resurrection
            
            return None
        
        def getPlayersResurrections(self,player):
            playersResurrections = []
            
            for resurrection in self.resurrections.values():
                if resurrection.user == player: playersResurrections.append(resurrection)
                
            return playersResurrections
        
        def getPlayersMostRecentResurrection(self,player):
            playersResurrections = self.getPlayersResurrections(player)
            highestIDNumber = playersResurrections[0].ID
            resWithHighestID = playersResurrections[0]
            
            for resurrection in playersResurrections:
                if highestIDNumber < resurrection.ID:
                    highestIDNumber = resurrection.ID
                    resWithHighestID = resurrection
                
            return resWithHighestID
        
        def isPlayersMostRecentResurrection(self,player,resurrection):
            return self.getPlayersMostRecentResurrection(player) == resurrection
        
        def playerHasDisconnected(self,player):
            for resurrection in self.getPlayersResurrections(player): resurrection.hasUserDisconnected = True
            
        def playerHasBeenKilled(self,player):
            for resurrection in self.getPlayersResurrections(player): resurrection.hasUserDied = True
            
        def playerHasExitedFriendlyREArea(self,area,player):
            resurrection = self.getREResurrection(player,area.GetGroupName())
            if resurrection != None: resurrection.proximityEnabled = False
            
        def playerHasCeasedTargettingRE(self,resurrectionP):
            for resurrection in self.resurrections.values():
                if resurrection.ID == resurrectionP.ID: resurrection.LRREnabled = False

    ''''
    This class is responsible for handling succesful and interrupted resurrections.
    '''
    class Resurrection:
        USED_RE_ICON = ""
        unusedID = 0
        
        def __init__(self,DADP,REP,userP,startedAtCloseRange):
            self.ID = DieAnotherDay.Resurrection.unusedID
            DieAnotherDay.Resurrection.unusedID += 1
            
            self.timer = None
            self.DAD = DADP
            self.RE = REP
            self.user = userP
            self.team = self.user.GetTeamNumber()
            self.timer = self.DAD.timerTracker.CreateTimer("ResurrectionTimer:" + self.getID())
            self.timer.SetUpdateCallback(self.ResurrectionHandler,1.0)
            self.timer.SetAgeRate(1.0,0)
            self.LRRMonitorExsists = False
            
            #Resurrection Interrupt Flags
            self.hasUserDisconnected = False
            self.hasUserDied = False
            self.LRREnabled = False
            self.proximityEnabled = False
            
            if startedAtCloseRange:  self.proximityEnabled = True
            else: self.LRREnabled = True
            
        def getID(self):
            return self.RE.ID + ":" + self.user.GetPlayerName()
        
        def start(self):
            if self.timer.state == Timer.STATE_STOP : self.timer.Start(self.DAD.resurrectionTime,False)
            else: GEUtil.DevWarning("Start() has been called for a resurrection which is already running, so it was ignored:" + self.getID() + "\n")
            return False
            
        def getRemainingTime(self):
            return self.DAD.resurrectionTime - self.timer.GetCurrentTime()
        
        def stop(self):
            self.resurrectionFailed()
        
        def resurrectionFailed(self):
            self.timer.Stop()
            self.RE.userCount -= 1
            
            #Delete the resurrection timer.
            self.DAD.timerTracker.RemoveTimer(self.timer.GetName())
            #Stop LRR Target Monitor
            if self.DAD.playersLRRTargetMonitor.has_key(self.user): 
                self.DAD.playersLRRTargetMonitor[self.user].delete()
                self.LRRMonitorExsists = False     
            #Remove Resurrection Progress Bar
            if self.hasUserDisconnected == False: GEUtil.RemoveHudProgressBar(self.user,DieAnotherDay.resurrectionPBIndex)
            
            #If nesscary, change the appearance of the RE to show its not being used:
            if self.DAD.REs.doesREExsist(self.RE.ID) and self.RE.used == False:
                if self.RE.userCount == 0: 
                    #Stop pulsating RE Rings
                    self.DAD.REs.stopPulsatingRings(self.RE.ID)
                    #Stop glow
                    #self.DAD.REs.disableREGlow(self.RE)
                    
                    #Make the objective icon become its normal colour
                    self.RE.clearObjective()
                    self.RE.setupObjective(self.team)
            
            #Delete this resurrection object
            self.DAD.resurrections.delete(self)
        
        #Everything that happens in successful and interrupted resurrections is implemented/called in this timer function:
        def ResurrectionHandler( self, timer, update_type ):
            #Resurrection failure response:
            if update_type != Timer.UPDATE_STOP:
                if self.RE.disabled or self.RE.used: self.timer.Stop()
                else:
                    if update_type == Timer.UPDATE_START:
                        #1. Start a LRR target monitor:
                        if self.LRREnabled:
                            LRRTargetMonitor = DieAnotherDay.LRRTargetMonitor(self)
                            LRRTargetMonitor.start()
                            self.LRRMonitorExsists = True
                        
                        self.RE.userCount += 1
                        if self.RE.userCount == 1:
                            #2. If this RE isn't already pulsating because of another resurrection:
                            self.DAD.REs.startPulsatingRings(self.RE.ID)
                            #Make the RE glow
                            #self.DAD.REs.makeREGlow(self.RE)
                            #3. Make the RE's objective icon become yellow, if it doesn't already look like this:
                            self.RE.clearObjective()
                            self.RE.setupYellowObjective()
                        #4. [Resurrection bar not already shown] Show the resurrection progress bar:
                        usersResCount = self.DAD.resurrections.getPlayersResurrectionCount(self.user)
                        if usersResCount == 1: GEUtil.InitHudProgressBar(self.user,self.DAD.resurrectionPBIndex,"1",GEGlobal.HUDPB_SHOWBAR,self.DAD.resurrectionTime,-1,DieAnotherDay.resBarY,120,16,self.DAD.getSidesColour(self.team))
                        else: GEUtil.UpdateHudProgressBar(self.user,self.DAD.resurrectionPBIndex,0,str(usersResCount),self.DAD.getSidesColour(self.team))
                    
                    elif update_type == Timer.UPDATE_RUN:
                        #If the resurrection has failed:
                        #TODO BUG singleplayer disconnect: RTTI error sometimes
                        if self.hasUserDisconnected or self.hasUserDied or self.team != self.user.GetTeamNumber(): self.resurrectionFailed()
                        elif self.LRREnabled == False and self.proximityEnabled == False: 
                            self.resurrectionFailed() #TESTED
                        #If it hasn't failed:
                        else:
                            #Enable/Disable a LRR target monitor if nesscary:
                            if self.LRREnabled and self.LRRMonitorExsists == False:
                                #Start a LRR target monitor:
                                LRRTargetMonitor = DieAnotherDay.LRRTargetMonitor(self)
                                LRRTargetMonitor.start()
                                self.LRRMonitorExsists = True
                            elif self.LRREnabled == False and self.LRRMonitorExsists:
                                #Stop LRR Target Monitor
                                self.DAD.playersLRRTargetMonitor[self.user].delete()
                                self.LRRMonitorExsists = False
                            
                            if self.DAD.resurrections.isPlayersMostRecentResurrection(self.user,self):
                                    #5. Update the resurrection progress bar:
                                    GEUtil.UpdateHudProgressBar(self.user,DieAnotherDay.resurrectionPBIndex,int(self.timer.GetCurrentTime()),str(self.DAD.resurrections.getPlayersResurrectionCount(self.user)))
                    #End a succesful resurrection:
                    elif update_type == Timer.UPDATE_FINISH: 
                        #6. Cancel the other resurrections for this resurrection's RE and prevent new resurrections from starting for it, before it's deleted.
                        self.DAD.REs.flagREAsUsed(self.RE.ID)
                        self.DAD.resurrections.cancelREResurrections(self.RE.ID,self.ID)
                        #7.Stop target monitor
                        if self.LRRMonitorExsists: self.DAD.playersLRRTargetMonitor[self.user].delete()
                        #8.Disable the RE and make it Invisible
                        self.RE.clearObjective()
                        self.RE.makeInvisible()
                        #9.Give the invisble RE an objective icon for the enemy team, to show them where a player was resurrected.
                        enemyTeam = GEGlobal.TEAM_MI6
                        if self.team == GEGlobal.TEAM_MI6: enemyTeam = GEGlobal.TEAM_JANUS
                        self.RE.clearObjective()
                        self.RE.setupObjective(enemyTeam)
                        #10. Delete the resurrection timer
                        self.DAD.timerTracker.RemoveTimer(self.timer.GetName())
                        #11.Stop pulsating RE Rings
                        self.RE.stopPulsating()
                        #12.Change REs Radar Icon to be the yellow Used RE icon
                        self.RE.changeRadarIcon("sprites/hud/radar/run",self.DAD.RQPositionColour)
                        #13.If the user has no other resurrections:
                        if self.DAD.resurrections.getPlayersResurrectionCount(self.user) == 1:
                            #14.Make the progress bar yellow for a moment and change the progress bar's resurrection count to 0:
                            GEUtil.UpdateHudProgressBar(self.user,self.DAD.resurrectionPBIndex,self.DAD.resurrectionTime,"0",DieAnotherDay.RQPositionColour)
                            #15.Remove the resurrection progress bar.
                            progressBarRemovalTimer = DieAnotherDay.ExtCallbackTimer(self.DAD.timerTracker,self.DAD.delayedResurrectionPBRemovalIfNoActiveResurrectionsAfterDelay,self.user)
                            progressBarRemovalTimer.start(3)
                        #16.Resurrect a player from the user's team
                        resurrectedPlayer = self.DAD.resurrectPlayerFromTeamIfTeamHasEliminatedPlayers(self.user)
                        if(resurrectedPlayer != None):
                            self.DAD.resurrectedPlayers.append(resurrectedPlayer)
                            
                            #17.Remove the resurrection queue position message from the resurrected player's screen.
                            GEUtil.removeHudProgressBar(resurrectedPlayer, DieAnotherDay.resQueueMessageChannel)
                            #18. Update the displayed survivor count for the resurrected player's team
                            if self.team == GEGlobal.TEAM_MI6: self.DAD.mSurvivorCountDisplay.OnTeamMemberResurrected()
                            else: self.DAD.jSurvivorCountDisplay.OnTeamMemberResurrected()
                            #19.Announce the resurrection.
                            playersName = resurrectedPlayer.GetPlayerName()
                            GEUtil.EmitGameplayEvent("DAD_Resurrection","%s" % playersName,"%i" % self.team,"%s" % self.user.GetPlayerName())
                            if self.team == GEGlobal.TEAM_MI6: GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_MI6_PLAYER_RESURRECTED",playersName)
                            else:GEUtil.ClientPrint(None,GEGlobal.HUD_PRINTTALK,"#GES_GP_DAD_JANUS_PLAYER_RESURRECTED",playersName)
                            #20.After a few seconds of being yellow, change the "used RE" icons colour to be the used RE's side's colour.
                            self.RE.changeRadarIconAfterDelay("sprites/hud/radar/run",self.DAD.getSidesRadarColour(self.team,False),3.0)
                            #21.After the "used RE" radar icon has not been yellow for X seconds, remove it and delete the RE.
                            self.DAD.REs.deleteREAfterDelay(self.RE.ID,10)
                        else: self.DAD.REs.deleteRE(self.RE.ID)
                        #22. Delete this resurrection object
                        self.DAD.resurrections.delete(self)