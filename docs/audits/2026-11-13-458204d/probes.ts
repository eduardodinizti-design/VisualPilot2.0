import { evaluatePreflopSpot } from '../../../src/utils/preflopEngine.ts';
import { evaluatePostflopSpot } from '../../../src/utils/postflopEngine.ts';
import { parseHandHistories } from '../../../src/utils/handParser.ts';
const pre:any={heroHand:'AA',heroPosition:'BTN',effectiveStackBB:40,scenario:'vs_open',limpersCount:2,openerPosition:'UTG',openSizeBB:2.3,icmStage:'chip_ev',bountyCoverBB:0,aggressionProfile:'balanced',hudSampleHands:0,hudFoldTo3Bet:50};
const post:any={street:'flop',potBB:6.5,effectiveStackBB:32,heroPosition:'IP',playersInPot:2,preflopInitiative:'hero_pfr',boardTexture:'dry_high',turnRiverCard:'brick',handCategory:'air',drawOuts:0,villainAction:'checked_to_hero',villainLine:'capped_check_back',blockerType:'blocks_nuts_value',aggressionProfile:'loose',bountyCoverBB:0,hudSampleHands:48,hudFoldToCbet:62,useMixedRng:true,rngRoll:99};
const compact=(d:any)=>({action:d.action,sizingBB:d.sizingBB,sizingLabel:d.sizingLabel,frequencies:d.frequencies,rngExecutedLine:d.rngExecutedLine,streetPlan:d.streetPlan});
const hh=`PokerStars Hand #123: Hold'em No Limit (0.50/1.00)
Table 'Audit' 2-max Seat #1 is the button
Seat 1: Hero (100 in chips)
Seat 2: Villain (100 in chips)
Hero: posts small blind 0.50
Villain: posts big blind 1.00
*** HOLE CARDS ***
Dealt to Hero [7c 2d]
Hero: folds
Villain collected 1.50 from pot
*** SUMMARY ***`;
const summarize=(text:string)=>{const h=parseHandHistories(text)[0];return {players:h.players,lastStep:h.steps.at(-1),firstStep:h.steps[0]};};
const a=evaluatePreflopSpot({...pre,openSizeBB:2});const b=evaluatePreflopSpot({...pre,openSizeBB:6});
const fold=evaluatePostflopSpot({...post,street:'river',handCategory:'air',villainAction:'facing_overbet',aggressionProfile:'tight',hudSampleHands:0});
const evidence={
 bbUnopened72o:compact(evaluatePreflopSpot({...pre,heroPosition:'BB',heroHand:'72o',scenario:'rfi'})),
 invalidHandFallsBackToAKs:{invalid:compact(evaluatePreflopSpot({...pre,heroHand:'??'})),AKs:compact(evaluatePreflopSpot({...pre,heroHand:'AKs'}))},
 fourBetExceedsStack:compact(evaluatePreflopSpot({...pre,scenario:'vs_3bet',openSizeBB:6})),
 allInLabelDifferentFromAmount:compact(evaluatePreflopSpot({...pre,openSizeBB:6})),
 openSizeDoesNotChange169Actions:{changed:Object.keys(a.matrixActions).filter(k=>a.matrixActions[k]!==b.matrixActions[k]).length},
 mixedStrategyDifferentFromAction:compact(evaluatePostflopSpot(post)),
 foldStillPlansBets:compact(fold),
 payoutRetainsPot:summarize(hh),
 summarySeatsOverwriteStacks:summarize(hh+'\nSeat 1: Hero (button) (small blind) folded before Flop\nSeat 2: Villain (big blind) collected (1.50)'),
 decimalComma:summarize(hh.replace('(100 in chips)','(2,50 in chips)')),
 matrixControls:{cells:Object.keys(a.matrixActions).length,percentage:a.rangeStats.totalCombosPct}
};
console.log(JSON.stringify(evidence,null,2));
