"""Offline probes of pinned upstream contracts, not model-quality evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

# Only satisfies upstream constructor validation. The API call is replaced below;
# this is an explicit offline fault-injection fixture, never an inference claim.
os.environ['OPENAI_API_KEY'] = 'offline-contract-fixture-not-a-real-key'
from contextual_long_term_reasoning.mind_palace_exploration import MindPalaceExploration, PlaceExploration
from contextual_long_term_reasoning.eqa_reasoning import EQAReasoning
from contextual_long_term_reasoning.belief_manager import WorldModel
from contextual_long_term_reasoning.mind_palace_generation import PlaceNode, RoomNode, SceneGraph

results = {'profile':'offline injected-response contract probes','upstream_revision':'b59be261f9508c3a355a8afa0d495eeba0417d68','live_api_calls':0,'gpu_used':False,'findings':[]}

def fake_api(payload):
    return NS(prepare_openai_vision_messages=lambda **kwargs: [], call_openai_api=lambda **kwargs: json.dumps(payload), answer_to_json=json.loads)

with contextlib.redirect_stdout(io.StringIO()):
    exploration=MindPalaceExploration()
    exploration.oa_interface=fake_api({'answer':'not found','reasoning':'Injected invalid enum fixture'})
    found,_=exploration.vlm_image_analysis([],NS(Q_user_question='fixture',y_object_to_search='fixture'))
    results['findings'].append({'id':'MP01','function':'MindPalaceExploration.vlm_image_analysis','input':{'answer':'not found'},'observed_found':found,'expected':'reject invalid enum','issue_reproduced':found is True})

    eqa=EQAReasoning()
    eqa.oa_interface=fake_api({'ready_to_answer':'not yes','answer_or_explanation':'Injected invalid enum fixture'})
    belief=NS(S_exploration_summary=['fixture'],Q_user_question='fixture',H_a_action_history=[],H_o_observation_history=[],M_mind_palace={'now':NS(room_nodes={'r1':NS(room_name='fixture')})},get_now_episode=lambda:'now')
    ready,_=eqa.check_ready_to_answer(belief)
    results['findings'].append({'id':'MP02','function':'EQAReasoning.check_ready_to_answer','input':{'ready_to_answer':'not yes'},'observed_ready':ready,'expected':'reject invalid enum','issue_reproduced':ready is True})

    planner=PlaceExploration()
    planner.direct_query_place_retrieval=lambda *args: []
    graph=NS(place_nodes={0:NS(room_parent='r1'),1:NS(room_parent='r1')})
    belief=NS(M_mind_palace={'past':graph},x_robot_location={},H_a_place_exploration_action_history=[],Q_user_question='fixture',y_object_to_search='fixture')
    selection=planner.plan(belief,'past','r1')
    results['findings'].append({'id':'MP03','function':'PlaceExploration.plan','input':{'direct_selection':[]},'observed_selection':selection,'expected':'fail or return an explicit unsupported/empty result without automatic substitute','issue_reproduced':selection==[0,1]})

    graph=NS(place_nodes={0:NS(position=[0,0,0]),1:NS(position=[1,0,0])})
    end,distance=WorldModel({'now':graph}).move_robot('now',99,[42])
    results['findings'].append({'id':'MP04','function':'WorldModel.move_robot','input':{'robot_place':99,'requested_places':[42]},'observed_end_place':end,'observed_distance':distance,'expected':'unknown IDs must fail; no physical execution inferred','issue_reproduced':end not in graph.place_nodes})

    place=PlaceNode(0,None,None,None)
    place.room_parent='r1'
    place.text_object_seen='offline schema fixture, not a model output'
    place.text_contextual_description='fixture'
    room=RoomNode('r1',None,None,None)
    room.room_name='Registered region fixture'
    room.text_object_seen='fixture'
    room.text_contextual_description='fixture'
    scene=SceneGraph('offline-unknown-pose','',{'r1':room},{0:place})
    text=scene.print_room_nodes()+scene.print_place_nodes()
    results['unknown_pose_formatting']={'status':'PASS_FORMATTING_ONLY','none_preserved':'None' in text,'claim':'Does not establish full reasoning or navigation compatibility with unknown geometry'}

Path('runs/mind-palace-fix-review-2026-11-01/contract-probes.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
