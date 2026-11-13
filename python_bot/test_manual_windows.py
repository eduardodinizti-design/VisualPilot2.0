import copy
import unittest
import numpy as np
from testar_windows import options,verify_pixels,key

class ManualTests(unittest.TestCase):
    def setUp(self):
        self.frame=np.zeros((30,40,3),np.uint8)
        self.meta=dict(status='SUCCESS',hwnd=12,pid=5,process_created=1,executable='PPPoker.exe',client_rect=[0,0,40,30],screen_origin=[-100,0],image_shape=[30,40,3])
        self.row=dict(status='COMPLETE_CANDIDATE',local_box=[2,3,30,25],hero_cards=['Ks','Tc'],board={'cards':[]},action_buttons=dict(status='EXPERIMENTAL_BUTTON_ROW',buttons=[dict(status='EXPERIMENTAL_LABEL',action='CALL',amount='1.0',unit='BB',box=[1,10,10,5])]))
        self.item=(self.row,self.row['action_buttons']['buttons'][0])
    def test_same_pixels(self):self.assertEqual(verify_pixels(self.frame,self.meta,self.frame.copy(),self.meta,self.item),(8,15))
    def test_changed_pixel(self):
        changed=self.frame.copy();changed[13,3]=255
        with self.assertRaises(RuntimeError):verify_pixels(self.frame,self.meta,changed,self.meta,self.item)
    def test_identity_and_geometry(self):
        for k,v in [('hwnd',13),('pid',6),('process_created',2),('screen_origin',[0,0]),('client_rect',[0,0,39,30])]:
            m=dict(self.meta);m[k]=v
            with self.assertRaises(RuntimeError):verify_pixels(self.frame,self.meta,self.frame,m,self.item)
    def test_failed_capture(self):
        with self.assertRaises(RuntimeError):verify_pixels(self.frame,self.meta,None,{},self.item)
    def test_preselect_and_unknown(self):
        self.assertEqual(len(options({'tables':[self.row]})),1)
        self.row['action_buttons']['status']='PRESELECTION_ROW'
        self.assertEqual(options({'tables':[self.row]}),[])
        self.row['action_buttons']['status']='EXPERIMENTAL_BUTTON_ROW'
        self.item[1]['status']='NOT_IDENTIFIED'
        self.assertEqual(options({'tables':[self.row]}),[])
    def test_amount_and_cards_change(self):
        other=copy.deepcopy(self.item);other[1]['amount']='2.0'
        self.assertNotEqual(key(self.item),key(other))
        other=copy.deepcopy(self.item);other[0]['hero_cards']=['As','Tc']
        self.assertNotEqual(key(self.item),key(other))
if __name__=='__main__':unittest.main()
