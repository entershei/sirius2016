from Bio.Align.Applications import ClustalOmegaCommandline
from Bio import SeqIO
from Bio import Seq
import argparse
import sys
import os.path


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file_in_good', help='input file [fasta]')
    parser.add_argument('--file_in_bad', help='input file [fasta]')
    parser.add_argument('--file_out', help='output file [fasta]')
    return parser


def viterbi(obs, states, start_p, trans_p, emit_p):
    V = [{}]

    for st in states:  # filling base
        try:
            V[0][st] = {"prob": start_p[st] * emit_p[st][obs[0]], "prev": None}
        except:
            V[0][st] = {"prob": 0, "prev": None}
    for t in range(1, len(obs)):  # filling dinamic
        V.append({})

        for st in states:
            max_tr_prob = 0

            for prev_st in states:
                try:
                    prob = V[t-1][prev_st]["prob"] * trans_p[prev_st][st]
                    max_tr_prob = max(prob, max_tr_prob)
                except:
                    pass

            for prev_st in states:
                try:
                    prob = V[t-1][prev_st]["prob"] * trans_p[prev_st][st]
                except:
                    prob = 0
                if prob == max_tr_prob:
                    try:
                        max_prob = max_tr_prob * emit_p[st][obs[t]]
                    except:
                        max_prob = 0
                    V[t][st] = {"prob": max_prob, "prev": prev_st}
                    break
            opt = []
    max_prob = max(value["prob"] for value in V[-1].values())
    previous = None

    for st, data in V[-1].items():  # regen path
        if data["prob"] == max_prob:
            opt.append(st)
            previous = st
            break

    for t in range(len(V) - 2, -1, -1):  # filling path
        opt.insert(0, V[t + 1][previous]["prev"])
        previous = V[t + 1][previous]["prev"]
    return (V, opt, max_prob)


def hamdist(str1, str2):
    diffs = 0

    for ch1, ch2 in zip(str1, str2):
        if ch1 != ch2:
            diffs += 1

    return diffs


def main():
    parser = get_parser()
    tmp = parser.parse_args()

    profile1 = tmp.file_in_good
    in_file = tmp.file_in_bad
    file_out = tmp.file_out
    out_dir = os.path.dirname(file_out)

    if not (profile1 and in_file and file_out):
        print(parser.usage())
        sys.exit(0)

    # Read bads
    bads = []
    LEN = 3
    for i in SeqIO.parse(in_file, format="fasta"):
        bads.append((i.id, str(i.seq)))
    number_of_bads = len(bads)

    for bad_id, bad in bads:
        print("Fixing %s" % bad_id)

        helpname = os.path.join(out_dir, 'help.fasta')
        help = open(helpname, 'w')
        help.write('>' + str(bad_id) + '\n')
        help.write(bad)
        help.close()
        print("\tHelp file created")

        # Profile alignment
        profile_alignment = os.path.join(out_dir, 'help.a.fasta')
        clustalomega_cline = ClustalOmegaCommandline(profile2=helpname,
                                                     profile1=profile1,
                                                     outfile=profile_alignment,
                                                     verbose=True, auto=True)
        clustalomega_cline()
        print("\tClustalOmega finished the alignment")

        # Read goods
        arr = []
        for i in SeqIO.parse(profile_alignment, format="fasta"):
            arr.append((i.id, str(i.seq)))
        good = list(map(lambda x: x[1], arr[:-1]))  # train
        aligned_bad = arr[-1][1]
        number_of_goods = len(good)

        with open(file_out, "wt") as fd:

            print("\tRemoving inserts started")
            position = 0
            bad_length = len(aligned_bad)
            while position != bad_length:  # removing inserts
                flag = True
                for good_number in range(number_of_goods):
                    if good[good_number][position] != '-':
                        flag = False
                if aligned_bad[position] != '-' and flag:
                    aligned_bad = aligned_bad[:position] + aligned_bad[position + 1:]
                    for good_number in range(number_of_goods):
                        good[good_number] = good[good_number][:position] + good[good_number][position + 1:]
                    position -= 1
                position += 1
            print("\tRemoving inserts ended")

            emit_p = dict()  # prob of transition from visible to hidden states
            trans_p = dict()  # prob of transition from hidden to hidden states
            start_p = dict()  # prob of starting states
            states = []  # hidden states
            statesset = set()  # done
            obs = []  # visible states
            start_p['0' + aligned_bad[:LEN]] = 1
            last = [aligned_bad[:LEN]]
            emit_p['0' + aligned_bad[:LEN]] = {'0' + aligned_bad[:LEN]: 1}
            print("\tMatrices construction started")
            for k in range(bad_length - LEN):
                s = aligned_bad[k:k + LEN]  # filling obs
                obs.append(str(k) + s)
                newlast = []

                # filling trans_p, emit_p and states
                for i in range(len(last)):
                    if aligned_bad[k + LEN] == '-':
                        arr = []
                        summ = 0
                        s1 = last[i] + aligned_bad[k + LEN]
                        s2 = str(k) + last[i]
                        for good_number in range(number_of_goods):
                            dist = hamdist(s1, good[good_number][k:k + LEN + 1])
                            arr.append((good[good_number][k + LEN], dist))
                            summ += dist
                        trans_p[s2] = dict()
                        states.append(s2)
                        statesset.add(s2)

                        for j in range(len(arr)):
                            s3 = str(k + 1) + last[i][1:] + arr[j][0]
                            s5 = str(k + 1) + aligned_bad[k + 1:k + LEN + 1]
                            p = 2 / number_of_goods - arr[j][1] / summ
                            if s3 not in trans_p[s2]:
                                trans_p[s2][s3] = p
                                emit_p[s3] = dict()
                                emit_p[s3][s5] = p
                                cond1 = k + 1 == bad_length - LEN
                                cond2 = s3 not in statesset
                                if cond1 and cond2:
                                    states.append(s3)
                                    statesset.add(s3)
                                if '-' not in last[i][1:] + arr[j][0]:
                                    newlast.append(last[i][1:] + arr[j][0])
                            else:
                                s4 = str(k + 1) + last[i][1:] + arr[j][0]
                                trans_p[s2][s4] += p
                                emit_p[s4][s5] += p
                    else:
                        s6 = str(k + 1) + last[i][1:] + aligned_bad[k + LEN]
                        trans_p[str(k) + last[i]] = dict()
                        trans_p[str(k) + last[i]][s6] = 1
                        states.append(str(k) + last[i])
                        statesset.add(str(k) + last[i])
                        emit_p[s6] = dict()
                        emit_p[s6][str(k + 1) + aligned_bad[k + 1:k + LEN + 1]] = 1
                        if k + 1 == bad_length - LEN and s6 not in statesset:
                            states.append(s6)
                            statesset.add(s6)
                        if '-' not in last[i][1:] + aligned_bad[k + LEN]:
                            newlast.append(last[i][1:] + aligned_bad[k + LEN])
                last = newlast
            obs.append(str(k + 1) + aligned_bad[k + 1:k + LEN + 1])
            print("\tMatrices construction ended")

            print("\tViterbi started")
            V, opt, max_prob = viterbi(obs, states, start_p, trans_p, emit_p)
            print("\tViterbi ended")
            ans = [opt[0][1:]]
            for i in opt[1:]:
                ans.append(i[-1])
            file_out.write('>%s\n' % bad_id)
            file_out.write('%s\n' % ''.join(ans))
            print("\tResults put into the file")

if __name__ == "__main__":
    main()
