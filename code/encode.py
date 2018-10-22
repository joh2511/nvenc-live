#!/bin/python3

# This file is used for reference. It's pretty quick, but not realtime.
# Part of the file builds up a literal string of bits (SPS, PPS, P-frames), while other parts
# conform more closely to normal BitString usage. It was easier to prototype by building up
# a string literal, but this was slow, so I switched to actual BitString functions for the
# very computationally expensive parts, but it was still too slow, so I abandoned it.

import bitstring as bs
import itertools
import math

CTU_SIZE = 32
OUTPUT_WIDTH = 3840
OUTPUT_HEIGHT = 1472

def getNAL(stream, nalNum):
    startIdx = stream.pos
    borders = list(stream.findall('0x000001', bytealigned=True, start=startIdx, count=2))
    stream.pos = startIdx
    nalBits = stream.read('bits:{}'.format(borders[1]-startIdx))
    return nalBits

def consumeBorder(stream, peek=False):
    return stream.read('bits:24')

def checkNALType(stream):
    # The border is 24 bits, then there's the 0 bit, then 6 bits for nal_unit_type
    nalTypeBits = stream.peek('bits:31').bin[-6:]
    nalType = nalTypeBits
    if nalTypeBits in ['000000', '000001']:
        nalType = 'P_frame'
    elif nalTypeBits in ['010011', '010100']:
        nalType = 'I_frame'
    elif nalTypeBits in ['100111', '101000']:
        nalType = 'SEI'
    elif nalTypeBits in ['100000', '100001', '100010']:
        nalType = 'PS'
    return nalType

def consumeNALRemainder(stream, nalString, doEmulationPrevention=True, newVersion=False, newNAL=None):
    if newVersion:
        # Now get the rest
        # First, get byte-aligned (in the original stream, NOT nalString)
        numToRead = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
        newNAL.append(stream.read('bits:{}'.format(numToRead)))
        # Go through the bytes, keeping an eye out for emulation_prevention_three_bytes
        zeroCounter = 0
        mostRecentByteCheck = -1
        while stream.pos < stream.len:
            if ((stream.len - stream.pos) < 8):
                numToRead = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
                newNAL.append(stream.read('bits:{}'.format(numToRead)))
            else:
                s = stream.read('bits:8').bin
                # emulation_prevention_three_byte must be byte-aligned
                if doEmulationPrevention and s == '00000011':
                    continue
                else:
                    newNAL.append('0b'+s)
                    # Make sure the most recent bytes weren't 0x0000. If they were, we need
                    # to do emulation prevention.
                    if doEmulationPrevention and newNAL.len > 16:
                        idx = (newNAL.len - (newNAL.len % 8)) - 16
                        if idx != mostRecentByteCheck:
                            mostRecentByteCheck = idx
                            chunk = newNAL[idx:idx+16].bin
                            if chunk == '0000000000000000':
                                newNAL.insert('0b00000011', idx+16)
                                #print(nalString)

        # Remove the previous byte alignment
        nalString = nalString[:nalString.rfind('1')]
        del newNAL[newNAL.rfind('0b1')[0]:]

        # Byte-align by appending a 1 and then 0s
        newNAL.append('0b1')
        numZeros = (8 - (newNAL.len % 8)) if (newNAL.len % 8 != 0) else 0
        if numZeros:
            newNAL.append('0b'+('0' * numZeros))

        return newNAL

    # Now get the rest
    # First, get byte-aligned (in the original stream, NOT nalString)
    numToRead = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
    nalString += stream.read('bits:{}'.format(numToRead)).bin
    # Go through the bytes, keeping an eye out for emulation_prevention_three_bytes
    zeroCounter = 0
    mostRecentByteCheck = -1
    while stream.pos < stream.len:
        if ((stream.len - stream.pos) < 8):
            numToRead = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
            s = stream.read('bits:{}'.format(numToRead)).bin
            nalString += s
        else:
            s = stream.read('bits:8').bin
            # emulation_prevention_three_byte must be byte-aligned
            if doEmulationPrevention and s == '00000011':
                continue
            else:
                nalString += s
                # Make sure the most recent bytes weren't 0x0000. If they were, we need
                # to do emulation prevention.
                if doEmulationPrevention and len(nalString) > 16:
                    idx = (len(nalString) - (len(nalString) % 8)) - 16
                    if idx != mostRecentByteCheck:
                        mostRecentByteCheck = idx
                        chunk = nalString[idx:idx+16]
                        if chunk == '0000000000000000':
                            nalString = nalString[:idx+16] + '00000011' + nalString[idx+16:]
                            #print(nalString)

    # Remove the previous byte alignment
    nalString = nalString[:nalString.rfind('1')]
    # Byte-align by appending a 1 and then 0s
    nalString += '1'
    numZeros = (8 - (len(nalString) % 8)) if (len(nalString) % 8 != 0) else 0
    nalString += '0' * numZeros

    return nalString

# Modify SPS as follows:
# - pic_width_in_luma_samples: set to the new pixel width
# - pic_height_in_luma_samples: set to the new pixel height
def modifySPS(stream, width=OUTPUT_WIDTH, height=OUTPUT_HEIGHT):
    spsString = ''
    # Consume border (0x000001 -> 4*6 = 24 bits)
    spsString += stream.read('bits:24').bin
    # Consume NAL header
    spsString += stream.read('bits:16').bin
    # Consume first 3 fields before profile_tier_level
    spsString += stream.read('bits:8').bin
    # Consume profile_tier_level
    # TODO ensure this is valid for all NVENC output
    spsString += stream.read('bits:84').bin
    # Consume next several until we get to pic width and height
    # TODO check for chroma_format_idc==3, assuming this is not true
    spsString += bs.Bits(ue=stream.read('ue')).bin
    spsString += bs.Bits(ue=stream.read('ue')).bin
    # Now consume the width and height fields and replace them with our own
    stream.read('ue')
    stream.read('ue')
    spsString += bs.Bits(ue=width).bin
    spsString += bs.Bits(ue=height).bin
    # Now get the rest
    spsString = consumeNALRemainder(stream, spsString)
    spsString = '0b' + spsString
    return bs.Bits(spsString), (width, height)

# Modify the PPS as follows:
# - set tiles_enabled_flag = 1
# - insert the 4 tile-related fields
def modifyPPS(stream, num_tile_rows=1, num_tile_cols=3):
    ppsString = ''
    # Consume border
    ppsString += stream.read('bits:24').bin
    # Consume NAL header
    ppsString += stream.read('bits:16').bin
    # Now consume PPS data until tiles_enabled_flag
    ppsString += bs.Bits(ue=stream.read('ue')).bin
    ppsString += bs.Bits(ue=stream.read('ue')).bin
    ppsString += stream.read('bits:7').bin
    ppsString += bs.Bits(ue=stream.read('ue')).bin
    ppsString += bs.Bits(ue=stream.read('ue')).bin
    ppsString += bs.Bits(ue=stream.read('se')).bin
    ppsString += stream.read('bits:3').bin
    ppsString += bs.Bits(ue=stream.read('ue')).bin
    ppsString += bs.Bits(ue=stream.read('se')).bin
    ppsString += bs.Bits(ue=stream.read('se')).bin
    ppsString += stream.read('bits:4').bin
    # Now we're at tiles_enabled_flag, so discard it, insert a 1 instead, then consume the
    # field right after so we can insert the tile info
    stream.read('bits:1')
    ppsString += '1'
    ppsString += stream.read('bits:1').bin
    # Insert the tile info
    ppsString += bs.Bits(ue=num_tile_cols-1).bin
    ppsString += bs.Bits(ue=num_tile_rows-1).bin
    ppsString += '10'
    # pps_loop_filter_across_slices_enabled_flag
    ppsString += stream.read('bits:1').bin
    # Now copy over the rest of the bits
    ppsString = consumeNALRemainder(stream, ppsString)
    ppsString = '0b' + ppsString
    return bs.Bits(ppsString)

# Modify an I-frame as follows:
# - segmentAddress
# - set slice_loop_filter_across_... = 0
# - insert num_entrypoint_offsets
def modifyIFrame(stream, isFirst, segmentAddress, ctuOffsetBitSize):
    newNAL = bs.BitArray()
    newNAL.append(stream.read('bits:42'))
    newNAL.append('0b'+bs.Bits(ue=stream.read('ue')).bin)
    if not isFirst:
        stream.read('bits:{}'.format(ctuOffsetBitSize))
        newNAL.append('0b'+bs.Bits(uint=segmentAddress, length=ctuOffsetBitSize).bin)
    newNAL.append('0b'+bs.Bits(ue=stream.read('ue')).bin)
    newNAL.append(stream.read('bits:2'))
    newNAL.append('0b'+bs.Bits(se=stream.read('se')).bin)
    # slice_loop_filter_across, num_entry_point, byte_align
    stream.read('bits:1')
    newNAL.append('0b011')
    numZeros = (8 - (len(newNAL) % 8)) if (len(newNAL) % 8 != 0) else 0
    newNAL.append('0b'+('0' * numZeros))
    # Remove the previous byte alignment
    stream.read('bits:1')
    numZeros = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
    stream.read('bits:{}'.format(numZeros))
    # Copy the rest of the I frame
    #iString = newNAL.bin
    consumeNALRemainder(stream, '', False, newVersion=True, newNAL=newNAL)
    #iString = '0b' + iString
    return newNAL

# Modify a P-frame as follows:
# - set slice_loop_filter_across_... = 0
# - insert num_entrypoint_offsets
def modifyPFrame(stream, isFirst, segmentAddress, ctuOffsetBitSize):
    pString = ''
    # Consume border (0x000001 -> 4*6 = 24 bits)01011101
    pString += stream.read('bits:24').bin
    # Consume NAL header
    pString += stream.read('bits:16').bin
    # Navigate to slice_loop_filter_across_... insertion spot
    pString += stream.read('bits:1').bin
    pString += bs.Bits(ue=stream.read('ue')).bin
    if not isFirst:
        stream.read('bits:{}'.format(ctuOffsetBitSize))
        pString += bs.Bits(uint=segmentAddress, length=ctuOffsetBitSize).bin
    pString += bs.Bits(ue=stream.read('ue')).bin # slice_type
    pString += stream.read('bits:8').bin # slice_pic_order_cnt_lsb
    pString += stream.read('bits:1').bin # short_term_ref_... assuming 0
    pString += stream.read('bits:1').bin # slice_sao_luma_flag
    pString += stream.read('bits:1').bin # slice_sao_chroma_flag
    pString += stream.read('bits:1').bin # num_ref_idx_active_override_flag
    pString += stream.read('bits:1').bin # cabac_init_flag
    pString += bs.Bits(ue=stream.read('ue')).bin # five_minus_max_num_...
    pString += bs.Bits(se=stream.read('se')).bin # slice_qp_delta
    # slice_loop_filter_across_...
    stream.read('bits:1')
    pString += '0'
    # Insert num_entry_point_offsets (Exp-Golomb)
    pString += '1'
    # byte_align() the header
    pString += '1'
    numZeros = (8 - (len(pString) % 8)) if (len(pString) % 8 != 0) else 0
    pString += '0' * numZeros
    # Remove the previous byte_alignment()
    stream.read('bits:1')
    numZeros = (8 - (stream.pos % 8)) if (stream.pos % 8 != 0) else 0
    stream.read('bits:{}'.format(numZeros))
    # Copy the rest of the P frame
    pString = consumeNALRemainder(stream, pString, False)
    pString = '0b' + pString
    return bs.Bits(pString)

if __name__=='__main__':
    NUM_FILES = 2
    NUM_SLICES = 3
    tileSizes = [-1 for _ in range(NUM_FILES)]
    with open('/home/trevor/Projects/hevc/videos/stitched.hevc', 'wb') as f:
        # Open each file
        files = [
            bs.BitStream(filename='/home/trevor/Projects/hevc/videos/ms9390_{}.hevc'.format(i))
            for i in range(NUM_FILES)
        ]
        borders = [list(bitstr.findall('0x000001', bytealigned=True)) for bitstr in files]
        files[0].pos = 0
        files[1].pos = 0
        # We only need PS info from one tile in the output stream header
        # VPS
        files[0].read('bits:{}'.format(borders[0][1])).tofile(f)
        #getNAL(files[0], 0).tofile(f)
        # SPS
        print('SPS')
        #sps, tileSizes[0] = modifySPS(getNAL(files[0], 1), OUTPUT_WIDTH, OUTPUT_HEIGHT)
        sps, tileSizes[0] = modifySPS(files[0].read('bits:{}'.format(borders[0][2] - files[0].pos)))
        sps.tofile(f)
        # PPS
        print('PPS')
        modifyPPS(getNAL(files[0], 2)).tofile(f)
        # SEI
        getNAL(files[0], 3).tofile(f)
        # Advance the other file, since we don't use its PS
        getNAL(files[1], 0)
        getNAL(files[1], 1)
        getNAL(files[1], 2)
        getNAL(files[1], 3)
        # Slice segment addresses
        tileCTUOffsets = [0, 40, 80]
        ctuOffsetBitSize = math.ceil(math.log((OUTPUT_WIDTH/CTU_SIZE)*(OUTPUT_HEIGHT/CTU_SIZE), 2))
        # Now do I and P frames until the end
        # Low quality on the sides, high quality in the middle
        i = 0
        nalNum = 4
        while True:
            for file_num, file_obj in enumerate(files):
                #print('i: ', i)
                nal = getNAL(file_obj, nalNum)
                nalNum += 1
                nalType = checkNALType(nal)
                if nalType == 'I_frame':
                    #print('I frame')
                    if (i==0 and file_num==1) or (i==1 and file_num==0) or (i==2 and file_num==1):
                        modifyIFrame(nal, i==0, tileCTUOffsets[i], ctuOffsetBitSize).tofile(f)
                    if file_num==1:
                        i += 1
                elif nalType == 'P_frame':
                    #print('P frame')
                    if (i==0 and file_num==1) or (i==1 and file_num==0) or (i==2 and file_num==1):
                        modifyPFrame(nal, i==0, tileCTUOffsets[i], ctuOffsetBitSize).tofile(f)
                    if file_num==1:
                        i += 1
                elif nalType == 'SEI':
                    #print('SEI')
                    if (file_num==0):
                        nal.tofile(f)
                    if file_num==1:
                        i = 0
                elif nalType == 'PS':
                    #print('PS (ignoring)')
                    continue
                else:
                    print('Error: invalid frame type "{}"'.format(nalType))
                    break