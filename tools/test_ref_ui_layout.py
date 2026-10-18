"""Invented fonts and layout inputs; no original game data in fixtures."""
import struct
import unittest

import ref_ui_layout as R


def font_fixture():
    go,ko,to = 0x214,0x244,0x250
    data=bytearray(to+0x40)
    struct.pack_into('<HHIIII',data,0,3,123,2,go,ko,to)
    struct.pack_into('<256h',data,0x14,*([-1]*256))
    struct.pack_into('<h',data,0x14+ord('A')*2,1)
    struct.pack_into('<h',data,0x14+ord('B')*2,2)
    for i,g in enumerate([(0,0,0,0,0,0,3,-1),(65,1,5,2,8,2,7,-1),(66,5,10,4,10,0,8,0)]):
        struct.pack_into('<H7h',data,go+i*16,*g)
    struct.pack_into('<HHhHHh',data,ko,1,2,-3,0,0,0)
    return data


class UiContracts(unittest.TestCase):
    def test_frame_borders_and_partial_tiles(self):
        calls=R.menu_frame(100,80,105,100,1)
        self.assertEqual(calls[:4], [R.Draw('btilebotleft.tex',100,147),R.Draw('btilebotright.tex',173,147),
                                    R.Draw('btiletopleft.tex',100,79),R.Draw('btiletopright.tex',173,79)])
        self.assertEqual(calls[6],R.Draw('btiletop.tex',164,80,(100,80,173,148)))
        self.assertEqual(calls[-1],R.Draw('btilecenter.tex',132,112,(100,80,173,148)))
        self.assertEqual(len(calls),13)

    def test_style2_overlap_and_inclusive_last_row(self):
        calls=R.menu_frame(100,80,105,100,2)
        self.assertEqual(calls[-1],R.Draw('tilecenter.tex',107,86,(100,80,199,174)))
        self.assertEqual(calls[5].clip,(100,80,177,180))
        centers=R.menu_frame(0,0,64,238,2,no_border=True)
        self.assertEqual([d.y for d in centers],[6,230])
        self.assertEqual(R.menu_frame(0,0,12,13,2,no_border=True),[])

    def test_suppression_and_small_frame_are_not_clamped(self):
        self.assertEqual(R.menu_frame(0,0,10,10,no_center=True,no_border=True),[])
        calls=R.menu_frame(0,0,10,10,1,no_center=True)
        self.assertEqual(calls[1],R.Draw('btilebotright.tex',-22,-23))
        self.assertEqual(len(calls),4)
        self.assertEqual(R.menu_frame(0,0,100,100,9),R.menu_frame(0,0,100,100,0))

    def test_network_local_promotion(self):
        self.assertEqual(R.hud_origins(),(12,478,167,323))
        self.assertEqual(R.hud_origins(True,(2,)),(167,478,12,323))
        self.assertEqual(R.hud_origins(True,(0,2)),(12,478,12,323))

    def test_whole_resource_rects(self):
        self.assertEqual(R.frame_source_rect('tilecenter.tex'),(0,0,320,224))
        self.assertEqual(R.frame_source_rect('ctiletop.tex'),(0,0,16,16))
        self.assertEqual(R.frame_source_rect('btileleft.tex'),(0,0,32,32))
        with self.assertRaises(ValueError): R.frame_source_rect('guessed.tex')

    def test_base_hud_layers_and_remote_variant(self):
        layers=R.hud_base_layers(12,44,1,4,2,4,50,0,100,cooldown=1)
        self.assertEqual([d.resource for d in layers],['bar_red00.tex','bar_green00.tex','bar_blue00.tex','hud_statusbar00.tex'])
        self.assertEqual([(d.x,d.y) for d in layers],[(27,46),(27,56),(27,63),(8,36)])
        self.assertEqual(layers[0].clip,(27,24,51,124))
        self.assertEqual(layers[2].tint,0x2aacacac)
        remote=R.hud_base_layers(478,43,1,1,0,0,local=False)
        self.assertEqual([d.resource for d in remote],['bar_red10.tex','hud_multi.tex'])
        self.assertEqual(remote[-1].x,474)

    def test_fill_length_truncates_and_does_not_clamp(self):
        self.assertEqual([R.bar_clip_right(27,n,4) for n in range(5)],[27,51,76,101,126])
        self.assertEqual(R.bar_clip_right(27,8,4),225)
        for current,maximum in [(0,0),(-1,2),(float('nan'),1),(1,float('inf'))]:
            with self.assertRaises(ValueError): R.bar_clip_right(27,current,maximum)

    def test_font_offsets_signed_kerning_and_unknown_header(self):
        font=R.parse_font(font_fixture())
        self.assertEqual((font.header_word,font.texture_offset,len(font.texture)),(123,0x250,64))
        self.assertEqual(font.glyphs[2][1:7],(5,10,4,10,0,8))
        self.assertEqual(font.kerns[0],(1,2,-3))
        self.assertEqual(font.glyph_rects(1,100,50),((1,2,4,6),(100,52,4,6)))
        self.assertEqual(font.width_ascii(b'AB'),12)
        self.assertEqual(font.width_ascii(b'AB',False),13)
        self.assertEqual(font.width_ascii(b'BA'),15)
        self.assertEqual(font.width_ascii(b'A?B'),18)
        self.assertEqual(font.width_ascii(b'AB\0BA'),12)
        self.assertEqual(font.width_ascii(b'AB',count=1),7)
        self.assertEqual(font.width_ascii(b'AB',count=0),0)

    def test_font_rejects_truncated_and_invalid_offsets(self):
        data=font_fixture()
        for end in [0,0x213,len(data)-1]:
            with self.assertRaises(ValueError): R.parse_font(data[:end])
        for offset,value in [(8,0),(12,0x215),(16,0xffffffff)]:
            bad=bytearray(data);struct.pack_into('<I',bad,offset,value)
            with self.assertRaises(ValueError): R.parse_font(bad)
        bad=bytearray(data);struct.pack_into('<h',bad,0x14,3)
        with self.assertRaises(ValueError):R.parse_font(bad)


if __name__ == '__main__': unittest.main()
